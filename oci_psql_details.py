#!/usr/bin/env python3
import sys
import json
import oci
from datetime import datetime, timedelta

CONFIG_PATH = "/home/zabbix/.oci/config"

def fetch_metric(monitoring_client, compartment_id, db_id, metric_name):
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=15)
    
    query = f'{metric_name}[1m]{{resourceId="{db_id}"}}.max()'
    
    details = oci.monitoring.models.SummarizeMetricsDataDetails(
        namespace="oci_postgresql",
        query=query,
        start_time=start_time,
        end_time=end_time
    )
    
    try:
        res = monitoring_client.summarize_metrics_data(compartment_id, details).data
        if res and res[0].aggregated_datapoints:
            return round(res[0].aggregated_datapoints[-1].value, 2)
    except Exception:
        pass
    return 0.0

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing DB System OCID"}))
        sys.exit(2)

    db_id = sys.argv[1]

    try:
        config = oci.config.from_file(file_location=CONFIG_PATH)
        psql_client = oci.psql.PostgresqlClient(config)
        db = psql_client.get_db_system(db_system_id=db_id).data
        
        monitoring_client = oci.monitoring.MonitoringClient(config)
        comp_id = db.compartment_id

        # Mapeia o status dos nos do cluster
        instances_status = {}
        active_nodes = 0
        if db.instances:
            for inst in db.instances:
                instances_status[inst.display_name] = inst.lifecycle_state
                if inst.lifecycle_state == "ACTIVE":
                    active_nodes += 1

        output = {
            "name": db.display_name,
            "lifecycle_state": db.lifecycle_state,
            "updown": "UP" if db.lifecycle_state == "ACTIVE" else "DOWN",
            "total_nodes": len(db.instances) if db.instances else 0,
            "active_nodes": active_nodes,
            "nodes_status": instances_status,
            "metrics": {}
        }

        # 1. Pergunta a OCI quais metricas existem para o Namespace do PostgreSQL
        list_details = oci.monitoring.models.ListMetricsDetails(namespace="oci_postgresql")
        metrics_response = monitoring_client.list_metrics(comp_id, list_details).data
        
        discovered_metrics = set()
        if metrics_response:
            for m in metrics_response:
                # Filtra apenas as metricas que pertencem a este banco de dados especifico
                if m.dimensions and m.dimensions.get("resourceId") == db_id:
                    discovered_metrics.add(m.name)
        
        # Fallback de seguranca caso o IAM do usuario limite o list_metrics
        if not discovered_metrics:
            discovered_metrics = [
                "CpuUtilization", "MemoryUtilization", "UsedStorage", "FreeStorage",
                "NetworkReceiveBytes", "NetworkTransmitBytes", "ReadIops", "WriteIops", 
                "ReadLatency", "WriteLatency", "Deadlocks", "ActiveConnections", "DiskQueueDepth"
            ]

        # 2. Coleta o valor de todas as metricas descobertas dinamicamente
        for metric in discovered_metrics:
            # Converte padrao CamelCase (CpuUtilization) para SnakeCase (cpu_utilization) do Zabbix
            key_name = ''.join(['_'+c.lower() if c.isupper() else c for c in metric]).lstrip('_')
            output["metrics"][key_name] = fetch_metric(monitoring_client, comp_id, db_id, metric)

        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)

if __name__ == "__main__":
    main() 

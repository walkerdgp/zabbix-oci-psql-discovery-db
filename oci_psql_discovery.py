#!/usr/bin/env python3
import sys
import json
import oci

CONFIG_PATH = "/home/zabbix/.oci/config"

def main():
    try:
        config = oci.config.from_file(file_location=CONFIG_PATH)
        identity_client = oci.identity.IdentityClient(config)
        psql_client = oci.psql.PostgresqlClient(config)

        tenancy_id = config["tenancy"]

        # Busca todos os compartments da Tenancy
        compartments = oci.pagination.list_call_get_all_results(
            identity_client.list_compartments,
            tenancy_id,
            compartment_id_in_subtree=True,
            access_level="ACCESSIBLE"
        ).data

        # Adiciona a própria Tenancy (Root Compartment) na lista de busca
        compartments.append(oci.identity.models.Compartment(id=tenancy_id, lifecycle_state="ACTIVE"))

        discovery_data = []

        for comp in compartments:
            if comp.lifecycle_state == "ACTIVE":
                try:
                    # Lista os bancos PaaS em cada compartment
                    db_systems = psql_client.list_db_systems(compartment_id=comp.id).data
                    for db in db_systems.items:
                        env = "Homologacao" if db.display_name.lower().startswith("bcoi") else "Producao"
                        discovery_data.append({
                            "{#HOSTNAME}": db.display_name.upper(),
                            "{#OCID}": db.id,
                            "{#ENVIRONMENT}": env
                        })
                except Exception:
                    pass # Ignora compartments sem bancos ou sem permissão de leitura

        print(json.dumps(discovery_data, indent=2))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)

if __name__ == "__main__":
    main()

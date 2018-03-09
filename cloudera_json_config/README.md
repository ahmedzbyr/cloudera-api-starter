# Configuration Information

Below are the service `json` response. These are just for reference.

## Curl Command.

    curl -u admin_username:admin_password "http://cloudera-manager-server.com:7180/api/v10/cm/config" > cm-config-deployment.json

## Cloudera Manager

- [`cloudera_manager/cm_full_config.json`](cloudera_manager/cm_full_config.json) - response to `http://cloudera-manager-server.com:7180/api/v15/cm/config?view=full` on the browser.
- [`cloudera_manager/cm_min_config.json`](cloudera_manager/cm_min_config.json) - reponse to `http://cloudera-manager-server.com:7180/api/v15/cm/config` on the browser.

## Zookeeper

- [`zookeeper/zookeeper_full_config.json`](zookeeper/zookeeper_full_config.json) - response to  `http://cloudera-manager-server.com:7180/api/v15/clusters/AutomatedHadoopCluster/services/ZOOKEEPER/config?view=full` on the browser.
- [`zookeeper/zookeeper_min_config.json`](zookeeper/zookeeper_min_config.json) - response to  `http://cloudera-manager-server.com:7180/api/v15/clusters/AutomatedHadoopCluster/services/ZOOKEEPER/config` on the browser.

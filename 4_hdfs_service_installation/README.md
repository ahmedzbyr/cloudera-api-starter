---
layout: post
title: Setting Up HDFS Services Using Cloudera API [Part 3]
category: linux cloudera hadoop cloudera-api zookeeper hdfs
pdf: false
tags: linux cloudera hadoop cloudera-api zookeeper hdfs
---

This is the second follow up post. In the earlier post 

- [`Setting Up Cloudera Manager Services Using Cloudera API [Part 1]`](https://ahmedzbyr.github.io/setting-up-cloudera-manager-services/) , We installed the cloudera management services. 
- [`Setting Up Zookeeper Services Using Cloudera API [Part 2]`](https://ahmedzbyr.github.io/setting-up-zookeeper-service-cloudera-api/) Installing Zookeeper service to the cluster.

Now we will be installing the HDFS service to our cluster.

1. Create a cluster.
2. Install `HDFS` service to our cluster.

**Creating a Cluster and setting up parcel is part of [earlier post](https://ahmedzbyr.github.io/setting-up-zookeeper-service-cloudera-api/).**


## Install HDFS Service.

`HDFS` service is installed in stages.

1. Create a `HDFS` service (if not exist).
2. Update configuration for our newly create `HDFS` service.
3. Create `HDFS` roles (`NAMENODE`, `SECONDARYNAMENODE`, `DATANODE`, `GATEWAY`) on the Cluster.
4. Format Namenode.
5. Start `HDFS` service.
6. Create Temporary `/tmp` directory in `HDFS`

### Create a `HDFS` service.

This is simple create a service if it does not exist.

``` python
def create_service(cluster):
    try:
        zk_service = cluster.get_service('HDFS')
        logging.debug("Service {0} already present on the cluster".format('HDFS'))
    except ApiException:
        #
        # Create service if it the first time.
        #
        zk_service = cluster.create_service('HDFS', 'HDFS')
        logging.info("Created New Service: HDFS")

    return zk_service
```

### Update configuration for `HDFS`.

This information is picked up from the configuration yaml file.

yaml file.

``` ruby
  HDFS:
    config:
      dfs_replication: 3
      dfs_permissions: false
      dfs_block_local_path_access_user: impala,hbase,mapred,spark
    roles:
      - group: NAMENODE
        hosts:
          - mycmhost.ahmed.com
        config:
          dfs_name_dir_list: /data/1/dfs/nn,/data/2/dfs/nn
          dfs_namenode_handler_count: 30
      - group: SECONDARYNAMENODE
        hosts:
          - mycmhost.ahmed.com
        config:
          fs_checkpoint_dir_list: /data/1/dfs/snn,/data/2/dfs/snn

      - group: DATANODE
        hosts:
          - mycmhost.ahmed.com
        config:
          dfs_data_dir_list: /data/1/dfs/dn,/data/2/dfs/dn
          dfs_datanode_handler_count: 30
          #dfs_datanode_du_reserved: 1073741824
          dfs_datanode_failed_volumes_tolerated: 0
          dfs_datanode_data_dir_perm: 755
      - group: GATEWAY
        hosts:
          - mycmhost.ahmed.com
        config:
          dfs_client_use_trash: true
```

Code snippet.

``` python
def service_update_configuration(zk_service):
    """
        Update service configurations
    :return:
    """
    zk_service.update_config(config['services']['HDFS']['config'])
    logging.info("Service Configuration Updated.")
```

### Create `HDFS` roles (`NAMENODE`, `SECONDARYNAMENODE`, `DATANODE`, `GATEWAY`) on the Cluster.

To create all the roles. 

- Each role needs to be unique on each host.
- We create a unique `role_name` for each node.

Each role is unique based on below set of strings. (`service_name`, `group`, `role_id`)

``` python
role_name = '{0}-{1}-{2}'.format(service_name, group, role_id)
```

Here is the code snippet.

``` python
def hdfs_create_cluster_services(config, service, service_name):
    """
        Creating Cluster services
    :return:
    """

    #
    # Get the role config for the group
    # Update group configuration and create roles.
    #
    for role in config['services'][service_name]['roles']:
        role_group = service.get_role_config_group("{0}-{1}-BASE".format(service_name, role['group']))
        #
        # Update the group's configuration.
        # [https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.role_config_groups.ApiRoleConfigGroup-class.html#update_config]
        #
        role_group.update_config(role.get('config', {}))
        #
        # Create roles now.
        #
        hdfs_create_roles(service, service_name, role, role['group'])
        
def hdfs_create_roles(service, service_name, role, group):
    """
    Create individual roles for all the hosts under a specific role group

    :param role: Role configuration from yaml
    :param group: Role group name
    """
    role_id = 0
    for host in role.get('hosts', []):
        role_id += 1
        role_name = '{0}-{1}-{2}'.format(service_name, group, role_id)
        logging.info("Creating Role name as: " + str(role_name))
        try:
            service.get_role(role_name)
        except ApiException:
            service.create_role(role_name, group, host)        
```


### Format Namenode.

First time when we create a HDFS environment we need to format namenode, this `init` the HDFS cluster.
`format_hdfs` method returns as `ApiCommand` which we can track progress of execution.

``` python
def format_namenode(hdfs_service, namenode):
    try:
        #
        # Formatting HDFS - this will have no affect the second time it runs.
        # Format NameNode instances of an HDFS service.
        #
        # https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.services.ApiService-class.html#format_hdfs
        #

        cmd = hdfs_service.format_hdfs(namenode)[0]
        logging.debug("Command Response: " + str(cmd))
        if not cmd.wait(300).success:
            print "WARNING: Failed to format HDFS, attempting to continue with the setup"
    except ApiException:
        logging.info("HDFS cannot be formatted. May be already in use.")
```

### Start `HDFS` service

We do this using the `service.start()` method. This method return  `ApiCommand` which we can track the progress and wait for the service to start using `cmd.wait().success`
More details about the Api [here](https://cloudera.github.io/cm_api/apidocs/v14/ns0_apiCommand.html)

Our service should be up and running. 


### Finally Creating `/tmp` directory on HDFS.

When we create a HDFS cluster we create a `/tmp` directory, HDFS /tmp directory is used as a temporary storage during mapreduce operation. 
Mapreduce artifacts, intermediate data will be kept under this directory. If we delete the `/tmp` contents then any MR jobs currently running will loose its current intermediate data. 

Any MR run after the `/tmp` is clear will still work without any issues.

Creating `/tmp` is done using `create_hdfs_tmp` method which returns `ApiCommand` response.

### Code Location

[Code - Setting Up HDFS Services Using Cloudera API [Part 3]](https://github.com/ahmedzbyr/getting_started_cloudera_api/tree/master/hdfs_service_installation)

### Useful Links.

- [Ansible Hadoop Playbook](https://github.com/objectrocket/ansible-hadoop)
- [Cloudera API Example](https://github.com/cloudera/cm_api/blob/master/python/examples/auto-deploy/deploycloudera.py)
- [Cloudera API](https://cloudera.github.io/cm_api/apidocs/v15/index.html)
- [Cloudera Epy Document](https://cloudera.github.io/cm_api/epydoc/5.10.0/index.html)
- [Cloudera API Getting Started](https://ahmedzbyr.github.io/getting-started-with-cloudera-api/)
- [Cloudera API Properties](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/Cloudera-Manager-Configuration-Properties.html)
- [Cloudera Manager Server Properties](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/cm5config_cmserver.html)
- [Cloudera Manager Service Properties](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/cm5config_mgmtservice.html)
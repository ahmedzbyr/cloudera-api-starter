---
layout: post
title: Setting Up Zookeeper Services Using Cloudera API [Part 2]
category: linux cloudera hadoop cloudera-api
pdf: false
tags: linux cloudera hadoop cloudera-api
---

This is the second follow up post. In the earlier post [`Setting Up Cloudera Manager Services Using Cloudera API [Part 1]`](https://github.com/ahmedzbyr/cloudera-api-starter/tree/master/2_cm_services_setup) we install the cloudera management services. Now we will be installing Zookeeper service to the cluster.

But first we need to to couple of things before we install Zookeeper.

1. Create a cluster.
2. Download, Distribute, Activate CDH Parcels.
3. Install Zookeeper service to our cluster.

## Creating a Cluster

First we create a cluster if it does not exists. Config details below.

``` python
def init_cluster(cm_api_handle):
    try:
        cluster = cm_api_handle.get_cluster(config['cluster']['name'])
        return cluster
    except ApiException:
        cluster = cm_api_handle.create_cluster(config['cluster']['name'],
                                                config['cluster']['version'],
                                                config['cluster']['fullVersion'])
```

If it is the first time then we need to add all the hosts to the cluster (including the admin node), this information is coming from the configuration yaml file. 

``` ruby
# Basic cluster information
cluster:
  name: AutomatedHadoopCluster
  version: CDH5
  fullVersion: 5.8.3
  hosts:
     - mycmhost.ahmed.com
```

In the above yaml snippet `hosts` will have all the hosts in the cluster, since we are testing on a VM with just one host we have that host added there.

``` python

    cluster_hosts = []
    #
    # Picking up all the nodes from the yaml configuration.
    #
    for host_in_cluster in cluster.list_hosts():
        cluster_hosts.append(host_in_cluster)

    hosts = []

    #
    # Create a host list, make sure we dont have duplicates.
    #
    for host in config['cluster']['hosts']:
        if host not in cluster_hosts:
            hosts.append(host)

    #
    # Adding all hosts to the cluster.
    #
    cluster.add_hosts(hosts)
    return cluster
```

Once we have the cluster ready then we can install the parcels to the cluster. 

##  Download, Distribute, Activate CDH Parcels

For Parcels there are three major methods which initiate the parcels distribution. 

1.  `parcel.start_download()` 
2.  `parcel.start_distribution()`
3.  `parcel.activate()`

These are the three methods which do all the work. When the `start_download` command is running we need to keep track of the progress, this is done using the `get_parcels` method.

`get_parcels` - [http://cloudera.github.io/cm_api/apidocs/v13/ns0_apiParcel.html](http://cloudera.github.io/cm_api/apidocs/v13/ns0_apiParcel.html) 

	#
	# When we execute and parcel download/distribute/activate command
	# we can track the progress using the `get_parcel` method.
	# This return a JSON described here : http://cloudera.github.io/cm_api/apidocs/v13/ns0_apiParcel.html
	# We can check progress by checking `stage`
	#
	#   AVAILABLE_REMOTELY: Stable stage - the parcel can be downloaded to the server.
	#   DOWNLOADING: Transient stage - the parcel is in the process of being downloaded to the server.
	#   DOWNLOADED: Stable stage - the parcel is downloaded and ready to be distributed or removed from the server.
	#   DISTRIBUTING: Transient stage - the parcel is being sent to all the hosts in the cluster.
	#   DISTRIBUTED: Stable stage - the parcel is on all the hosts in the cluster. The parcel can now be activated, or removed from all the hosts.
	#   UNDISTRIBUTING: Transient stage - the parcel is being removed from all the hosts in the cluster>
	#   ACTIVATING: Transient stage - the parcel is being activated on the hosts in the cluster. New in API v7
	#   ACTIVATED: Steady stage - the parcel is set to active on every host in the cluster. If desired, a parcel can be deactivated from this stage.
	#

We track the progress of each stage using the snippet below.


``` python 
def check_current_state(cluster, product, version, states):
    logging.info("Checking Status for Parcel.")
    while True:
        parcel = cluster.get_parcel(product, version)
        logging.info("Parcel Current Stage: " + str(parcel.stage))
        if parcel.stage in states:
            break
        if parcel.state.errors:
            raise Exception(str(parcel.state.errors))

        logging.info("%s progress: %s / %s" % (states[0], parcel.state.progress,
                                               parcel.state.totalProgress))
        time.sleep(15)
```

Rest of the parcel execute is straight forward.

## Install Zookeeper Service.

Zookeeper service is installed in stages.

1. Create a service (if not exist)
2. Update configuration for our newly create Zookeeper service.
3. Create Zookeeper role (`SERVER`) on the Cluster.
4. Initalize Zookeeper using the `init_zookeeper()` command.
5. Start Zookeeper service.

### Create a service.

This is simple create a service if it does not exist.

``` python
def zk_create_service(cluster):
    try:
        zk_service = cluster.get_service('ZOOKEEPER')
        logging.debug("Service {0} already present on the cluster".format(self.name))
    except ApiException:
        #
        # Create service if it the first time.
        #
        zk_service = cluster.create_service('ZOOKEEPER', 'ZOOKEEPER')
        logging.info("Created New Service: ZOOKEEPER")

    return zk_service
```

### Update configuration for Zookeeper.

This information is picked up from the configuration yaml file.

yaml file.

``` ruby
  ZOOKEEPER:
    config:
      zookeeper_datadir_autocreate: true
```

Code snippet.

``` python
def zk_update_configuration(zk_service):
    """
        Update service configurations
    :return:
    """
    zk_service.update_config(config['services']['ZOOKEEPER']['config'])
    logging.info("Service Configuration Updated.")
```

### Create Zookeeper role (`SERVER`) on the Cluster.

This is the important part, here we create Zookeeper roles `SERVER` (each instance of zookeeper on each server is referred as a `SERVER` role).

Role names should be unique, we combine the `service_name`, `role`, `zookeeper_id` to form a unique identifier. Example : Here it would be `ZOOKEEPER-SERVER-1` 


Here is the code snippet.

``` python
zookeeper_host_id = 0

    #
    # Configure all the host.
    #
    for zookeeper_host in config['services']['ZOOKEEPER']['roles'][0]['hosts']:
        zookeeper_host_id += 1
        zookeeper_role_config = config['services']['ZOOKEEPER']['roles'][0]['config']
        role_name = "{0}-{1}-{2}".format('ZOOKEEPER', 'SERVER', zookeeper_host_id)
```

Next once we create the `role` we update the configuration which we get from the `yaml` file. 

Yaml file.

``` ruby 
roles:
  - group: SERVER
    hosts:
      - mycmhost.ahmed.com
    config:
      quorumPort: 2888
      electionPort: 3888
      dataLogDir: /var/lib/zookeeper
      dataDir: /var/lib/zookeeper
```

Code snippet.

``` python
#
# Configuring Zookeeper server ID
#
zookeeper_role_config['serverId'] = zookeeper_host_id

#
# Update configuration
#
role.update_config(zookeeper_role_config)
```
Now we are set to start the Zookeeper.

### Initalize Zookeeper using the `init_zookeeper()` command.

Before we start Zookeeper we need to init the service, which create `id` for each service running on each server. ps: it creates the my_id for each service in `/var/lib/zookeeper` location. This will help each Zookeeper identify itself as unique. 

If there were 3 Zookeeper servers (which is minimum recommended) we would have something like below.

1. Role `ZOOKEEPER-SERVER-1`, Server `1`, Zookeeper ID `my_id` `1`
2. Role `ZOOKEEPER-SERVER-2`, Server `2`, Zookeeper ID `my_id` `2`
3. Role `ZOOKEEPER-SERVER-3`, Server `3`, Zookeeper ID `my_id` `3`

And so on. 

Once we have the service initialized we are ready to start the service.

### Start Zookeeper service

We do this using the `zk_service.start()` method. This method return  `ApiCommand` which we can track the progress and wait for the service to start using `cmd.wait().success`

More details about the Api [here](https://cloudera.github.io/cm_api/apidocs/v14/ns0_apiCommand.html)

Our service should be up and running. 

### Yaml File

[Cloudera Zookeeper Yaml File](https://github.com/ahmedzbyr/cloudera-api-starter/blob/master/3_parcels_and_zookeeper_service_installation/cloudera_zookeeper.yaml)

### Code File.

[Cloudera Zookeeper Service Code File](https://github.com/ahmedzbyr/cloudera-api-starter/blob/master/3_parcels_and_zookeeper_service_installation/cdh_cluster_parcel_zookeeper_service.py)


### Executing Code

[VIDEO - Setting Up Zookeeper Services Using Cloudera API \[Part 2\]](https://www.youtube.com/watch?v=1bJKBmdQ7J0)

### Useful Links.

- [Ansible Hadoop Playbook](https://github.com/objectrocket/ansible-hadoop)
- [Cloudera API Example](https://github.com/cloudera/cm_api/blob/master/python/examples/auto-deploy/deploycloudera.py)
- [Cloudera API](https://cloudera.github.io/cm_api/apidocs/v15/index.html)
- [Cloudera Epy Document](https://cloudera.github.io/cm_api/epydoc/5.10.0/index.html)
- [Cloudera API Getting Started](https://ahmedzbyr.github.io/getting-started-with-cloudera-api/)
- [Cloudera API Properties](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/Cloudera-Manager-Configuration-Properties.html)
- [Cloudera Manager Server Properties](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/cm5config_cmserver.html)
- [Cloudera Manager Service Properties](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/cm5config_mgmtservice.html)

---
layout: post
title: Getting Started with Cloudera API
category: linux cloudera hadoop cloudera-api
pdf: false
tags: linux cloudera hadoop cloudera-api
---

This is a basic steps to get connected with cloudera manager.

Here are some of the cool things you can do with [Cloudera Manager via the API](https://cloudera.github.io/cm_api/):

- Deploy an entire Hadoop cluster programmatically. Cloudera Manager supports HDFS, MapReduce, YARN, ZooKeeper, HBase, Hive, Oozie, Hue, Flume, Impala, Solr, Sqoop, Spark and Accumulo.
- Configure various Hadoop services and get config validation.
- Take admin actions on services and roles, such as start, stop, restart, failover, etc. Also available are the more advanced workflows, such as setting up high availability and decommissioning.
- Monitor your services and hosts, with intelligent service health checks and metrics.
- Monitor user jobs and other cluster activities.
- Retrieve timeseries metric data.
- Search for events in the Hadoop system.
- Administer Cloudera Manager itself.
- Download the entire deployment description of your Hadoop cluster in a json file.

Additionally, with the appropriate licenses, the API lets you:
 
- Perform rolling restart and rolling upgrade.
- Audit user activities and accesses in Hadoop.
- Perform backup and cross data-center replication for HDFS and Hive.
- Retrieve per-user HDFS usage report and per-user MapReduce resource usage report.


## API Installations.

- Install `python-pip`
- Install `cm-api`

We will be using centos 6 to setup our environment.

	sudo yum install python-pip
	sudo pip install cm-api

## Useful Links.

- [Epydoc](https://cloudera.github.io/cm_api/epydoc/5.10.0/index.html)
- [Cloudera Manager Properties 5.0.0](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/cm5config_cdh500.html)
- [Cloudera API v13](https://cloudera.github.io/cm_api/apidocs/v13/index.html)


## Getting Connected To Cloudera Manager.

First we get a API handle to use to connect to `Cloudera Manager Services` and `Cluster Services`. `config` is coming from a `yaml` file.

	@property
	def cm_api_handle(self):
	
	    """
	        This method is to create a handle to CM.
	    :return: cm_api_handle
	    """
	    if self._cm_api_handle is None:
	        self._cm_api_handle = ApiResource(self.config['cm']['host'],
	                                          self.config['cm']['port'],
	                                          self.config['cm']['username'],
	                                          self.config['cm']['password'],
	                                          self.config['cm']['tls'],
	                                          version=self.config['cm']['api-version'])
	    return self._cm_api_handle

A simple way to write it would be as below. (I am using version=13 here)


	cm_api_handle = api = ApiResource(cm_host, username="admin", password="admin", version=13)

Now we can use this handle to connect to CM or Cluster. Now lets look at what we can do once we have the `cloudera_manager` object.

We can do all these method calls on this. [CM Class](https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.cms.ClouderaManager-class.html)

	cloudera_manager = cm_api_handle.get_cloudera_manager()
	cloudera_manager.get_license()
	
	cm_api_response = cloudera_manager.get_services()
	
Here API response `cm_api_response` would be [APIService](https://cloudera.github.io/cm_api/apidocs/v15/ns0_apiService.html)

Similarly we get [cluster methods](https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.clusters.ApiCluster-class.html) for the cluster but in a List format as there are many services on the cluster.

	cloudera_cluster = cm_api_handle.get_cluster("CLUSTER_NAME")
	cluster_api_response = cloudera_cluster.get_all_services()

Again the response would be a ApiService.

## Example Code to get started.

First lets create a yaml file.
	
``` ruby
# Cloudera Manager config
cm:
  host: 127.0.0.1
  port: 7180
  username: admin
  password: admin
  tls: false
  version: 13

# Basic cluster information
cluster:
  name: AutomatedHadoopCluster
  version: CDH5
  fullVersion: 5.8.3
  hosts:
     - 127.0.0.1
```

Next we create script to process that data.

``` python
import yaml
import sys
from cm_api.api_client import ApiResource, ApiException


def fail(msg):
    print (msg)
    sys.exit(1)

if __name__ == '__main__':

    try:
        with open('cloudera.yaml', 'r') as cluster_yaml:
            config = yaml.load(cluster_yaml)

        api_handle = ApiResource(config['cm']['host'],
                                 config['cm']['port'],
                                 config['cm']['username'],
                                 config['cm']['password'],
                                 config['cm']['tls'],
                                 version=config['cm']['version'])

        # Checking CM services
        cloudera_manager = api_handle.get_cloudera_manager()
        cm_api_response = cloudera_manager.get_service()

        print "\nCLOUDERA MANAGER SERVICES\n----------------------------"
        print "Complete ApiService: " + str(cm_api_response)
        print "Check URL for details : https://cloudera.github.io/cm_api/apidocs/v15/ns0_apiService.html"
        print "name: " + str(cm_api_response.name)
        print "type: " + str(cm_api_response.type)
        print "serviceUrl: " + str(cm_api_response.serviceUrl)
        print "roleInstancesUrl: " + str(cm_api_response.roleInstancesUrl)
        print "displayName: " + str(cm_api_response.displayName)

        # Checking Cluster services
        cm_cluster = api_handle.get_cluster(config['cluster']['name'])
        cluster_api_response = cm_cluster.get_all_services()
        print "\n\nCLUSTER SERVICES\n----------------------------"
        for api_service_list in cluster_api_response:
            print "Complete ApiService: " + str(api_service_list)
            print "Check URL for details : https://cloudera.github.io/cm_api/apidocs/v15/ns0_apiService.html"
            print "name: " + str(api_service_list.name)
            print "type: " + str(api_service_list.type)
            print "serviceUrl: " + str(api_service_list.serviceUrl)
            print "roleInstancesUrl: " + str(api_service_list.roleInstancesUrl)
            print "displayName: " + str(api_service_list.displayName)

    except IOError as e:
        fail("Error creating cluster {}".format(e))
```

Output

``` sh
CLOUDERA MANAGER SERVICES
----------------------------
Complete ApiService: <ApiService>: mgmt (cluster: None)
Check URL for details : https://cloudera.github.io/cm_api/apidocs/v15/ns0_apiService.html
name: mgmt
type: MGMT
serviceUrl: http://mycmhost.ahmed.com:7180/cmf/serviceRedirect/mgmt
roleInstancesUrl: http://mycmhost.ahmed.com:7180/cmf/serviceRedirect/mgmt/instances
displayName: Cloudera Management Service


CLUSTER SERVICES
----------------------------
Complete ApiService: <ApiService>: ZOOKEEPER (cluster: AutomatedHadoopCluster)
Check URL for details : https://cloudera.github.io/cm_api/apidocs/v15/ns0_apiService.html
name: ZOOKEEPER
type: ZOOKEEPER
serviceUrl: http://mycmhost.ahmed.com:7180/cmf/serviceRedirect/ZOOKEEPER
roleInstancesUrl: http://mycmhost.ahmed.com:7180/cmf/serviceRedirect/ZOOKEEPER/instances
displayName: ZOOKEEPER
```

This is the basics, we will be build on top of this in coming blog posts.
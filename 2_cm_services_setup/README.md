---
layout: post
title: Setting Up Cloudera Manager Services Using Cloudera API [Part 1]
category: linux cloudera hadoop cloudera-api
pdf: false
tags: linux cloudera hadoop cloudera-api
---


Cloudera API is a very convenient way to setup a cluster and do more. 

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


### Prerequisites [IMPORTANT]

**Assuming initial setup is complete. [Cloudera Manager Setup Using Chef](https://ahmedzbyr.github.io/chef-cloudera-manager-install-setup/)**

1. Mysql is install and all databases are created.
2. Cloudera Manager server is installed and configured.
3. Cloudera Manager repo is setup (optional if you are using internal repo else update yaml)

### Before we start.

**NOTE: We will be using Mysql for database and will assume that the database is already installed and all the necessary databases are created with users.** 

1. We need to understand the services and setup configuration for each service.
2. Setup database configuration.


### Currently we will be doing below operation in this post.

- Install Hosts.
- Setup `Cloudera Manager Services` using API.
    - Activity Monitor
    - Alert Publisher
    - Event Server
    - Host Monitor
    - Reports Manager
    - Service Monitor

### Steps for the current task.

1. Set License (or set trial for the setup)
2. Install Hosts
3. Configure and setup all the services above.
3. Start Services on cloudera manager. 



### Activity Monitor

Cloudera Manager's activity monitoring capability monitors the MapReduce, Pig, Hive, Oozie, and streaming jobs, Impala queries, and YARN applications running or that have run on your cluster. When the individual jobs are part of larger workflows (using Oozie, Hive, or Pig), these jobs are aggregated into MapReduce jobs that can be monitored as a whole, as well as by the component jobs. [Courtesy Cloudera Website](https://www.cloudera.com/documentation/enterprise/5-8-x/topics/cm_dg_activity_monitoring.html)

The following sections describe how to view and monitor activities that run on your cluster.

- [Monitoring MapReduce Jobs](https://www.cloudera.com/documentation/enterprise/5-8-x/topics/cm_dg_activities.html#cmug_topic_8_1)
- [Monitoring Impala Queries](https://www.cloudera.com/documentation/enterprise/5-8-x/topics/cm_dg_impala_queries.html#cm_impala_queries)
- [Monitoring YARN Applications](https://www.cloudera.com/documentation/enterprise/5-8-x/topics/cm_dg_yarn_applications.html#xd_583c10bfdbd326ba--43d5fd93-1410993f8c2--7fc8)
- [Monitoring Spark Applications](https://www.cloudera.com/documentation/enterprise/5-8-x/topics/operation_spark_applications.html#spark_monitoring)

#### Configuration Setup Information for Activity Monitor.

Complete details about the configuration. [Cloudera Activity Monitor](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/cm5config_mgmtservice.html)

``` json
{
  'config': {
    'firehose_database_host': 'server-admin-node.ahmedinc.com:3306',
    'firehose_database_password': 'amon_password',
    'firehose_database_user': 'amon',
    'firehose_database_type': 'mysql',
    'firehose_database_name': 'amon'
  },
  'hosts': [
    'server-admin-node.ahmedinc.com'
  ],
  'group': 'ACTIVITYMONITOR'
}
```

For activity monitor we need to set the database and will leave other configuration as default which cloudera manager will take care. Activity monitor was earlier called as `firehose`. So the configuration information still has `firehose` in it.

- Group Name `ACTIVITYMONITOR` (This the information which cloudera manager uses to know which service it needs to create)
- DB Host `admin-node` or the node which is hosting the `mysql` database.


### Reports Manager

The Reports page lets you create reports about the usage of HDFS in your cluster—data size and file count by user, group, or directory. It also lets you report on the MapReduce activity in your cluster, by user.


``` json
'config': {
	'headlamp_database_name': 'rman',
	'headlamp_database_user': 'rman',
	'headlamp_database_type': 'mysql',
	'headlamp_database_password': 'rman_password',
	'headlamp_database_host': 'server-admin-node.ahmedinc.com:3306'
},
	'hosts': [
	'server-admin-node.ahmedinc.com'
	],
	'group': 'REPORTSMANAGER'
```

- Group Name `REPORTSMANAGER` (This the information which cloudera manager uses to know which service it needs to create)

### Rest of the service Alert Publiser, Event Server, Host Monitor, Service Monitor

- **Alert Publisher** can be to send alert notifications by email or by SNMP trap to a trap receiver.
- **Event Server** aggregates relevant events and makes them available for alerting and for searching. This way, you have a view into the history of all relevant events that occur cluster-wide.
- **Host Monitoring** features let you manage and monitor the status of the hosts in your clusters.
- **Service Monitoring** feature monitors dozens of service health and performance metrics about the services and role instances running on your cluster:
	- Presents health and performance data in a variety of formats including interactive charts
	- Monitors metrics against configurable thresholds
	- Generates events related to system and service health and critical log entries and makes them available for searching and alerting
	- Maintains a complete record of service-related actions and configuration changes

Group Names : `ALERTPUBLISHER`, `EVENTSERVER`, `HOSTMONITOR`, `SERVICEMONITOR`


## Creating Script For Deploying Cloudera Management Services. 

Tasks we need to work on.

1. Create a configuration JSON file. (We will be using the same JSON above)
2. Setup license for the cluster (we will be setting trial version)
3. Install Hosts.
4. Initialize Cluster for the First time.
5. Deploy Management Roles (Update service configuration and create roles for each service).

### Creating JSON file.

Host Installation

``` json
'cm_host_installation': {
	'host_cm_repo_gpg_key_custom_url': 'http://192.168.0.115/cm5/redhat/6/x86_64/cm/RPM-GPG-KEY-cloudera',
	'host_java_install_strategy': 'AUTO',
	'host_cm_repo_url': 'http://192.168.0.115/cm5/redhat/6/x86_64/cm/5/',
	'host_unlimited_jce_policy': True,
	'host_password': 'Bigdata@123',
	'host_username': 'cmadmin',
	'ssh_port': 22
}
```

Cloudera Manager Credentials and Remote Repo setup. 

``` json
'cm': {
	'username': 'admin',
	'tls': False,
	'host': 'server-admin-node.ahmedinc.com',
	'api-version': 13,
	'remote_parcel_repo_urls': 'http://192.168.0.115/cdh5/parcels/5.8.3,http://192.168.0.115/accumulo/parcels/1.4/,http://192.168.0.115/accumulo-c5/parcels/latest/,http://192.168.0.115/kafka/parcels/latest/,http://192.168.0.115/navigator-keytrustee5/parcels/latest/,http://192.168.0.115/spark/parcels/latest/,http://192.168.0.115/sqoop-connectors/parcels/latest/',
	'password': 'admin',
	'port': 7180
}
```

Cluster Information.

``` json
'cluster': {
	'version': 'CDH5',
	'hosts': [
	  'server-admin-node.ahmedinc.com',
	  'server-edge-node.ahmedinc.com',
	  'server-worker-node.ahmedinc.com'
	],
	'name': 'AutomatedHadoopCluster',
	'fullVersion': '5.8.3'
}
```

Management Service.

``` json
'MGMT': {
      'roles': [
        {
          'config': {
            'firehose_database_host': 'server-admin-node.ahmedinc.com:3306',
            'firehose_database_password': 'amon_password',
            'firehose_database_user': 'amon',
            'firehose_database_type': 'mysql',
            'firehose_database_name': 'amon'
          },
          'hosts': [
            'server-admin-node.ahmedinc.com'
          ],
          'group': 'ACTIVITYMONITOR'
        },
        {
          'group': 'ALERTPUBLISHER',
          'hosts': [
            'server-admin-node.ahmedinc.com'
          ]
        },
        {
          'group': 'EVENTSERVER',
          'hosts': [
            'server-admin-node.ahmedinc.com'
          ]
        },
        {
          'group': 'HOSTMONITOR',
          'hosts': [
            'server-admin-node.ahmedinc.com'
          ]
        },
        {
          'group': 'SERVICEMONITOR',
          'hosts': [
            'server-admin-node.ahmedinc.com'
          ]
        },
        {
          'config': {
            'headlamp_database_name': 'rman',
            'headlamp_database_user': 'rman',
            'headlamp_database_type': 'mysql',
            'headlamp_database_password': 'rman_password',
            'headlamp_database_host': 'server-admin-node.ahmedinc.com:3306'
          },
          'hosts': [
            'server-admin-node.ahmedinc.com'
          ],
          'group': 'REPORTSMANAGER'
        }
      ]
    }
```


### License Update.

First we get license for the cluster, if we receive an exception the we set trial version.

``` python
def enable_license_for_cm(cloudera_manager)
	try:
	    # Check for current License.
	    cloudera_license = cloudera_manager.get_license()
	except ApiException:
		# If we recieve an exception, then this is first time we are setting the license
	    cloudera_manager.begin_trial()
```

### Installing Hosts.


Once we have set the lic installed, we need to setup the hosts to have all the services running. `host_install` command will install all the services like `agent`, `daemon`, `java` and `jce_policy` files. This will also configure the hosts to contact the admin-node for heartbeat. 

Below is a code snippet to install hosts. 


``` python
def host_installation(cloudera_manager, config):
    """
        Host installation.
        https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.cms.ClouderaManager-class.html#host_install
    """
    logging.info("Installing HOSTs.")
    cmd = cloudera_manager.host_install(config['cm_host_installation']['host_username'],
                                   config['cluster']['hosts'],
                                   ssh_port=config['cm_host_installation']['ssh_port'],
                                   password=config['cm_host_installation']['host_password'],
                                   parallel_install_count=10,
                                   cm_repo_url=config['cm_host_installation']['host_cm_repo_url'],
                                   gpg_key_custom_url=config['cm_host_installation']['host_cm_repo_gpg_key_custom_url'],
                                   java_install_strategy=config['cm_host_installation']['host_java_install_strategy'],
                                   unlimited_jce=config['cm_host_installation']['host_unlimited_jce_policy'])

    #
    # Check command to complete.
    #
    if not cmd.wait().success:
        logging.info("Command `host_install` Failed. {0}".format(cmd.resultMessage))
        if (cmd.resultMessage is not None and
                    'There is already a pending command on this entity' in cmd.resultMessage):
            raise Exception("HOST INSTALLATION FAILED.")
```

### Deploy Management Services.

First we need to create a management services if it does not exsist.

``` python
mgmt_service = cloudera_manager.create_mgmt_service(ApiServiceSetupInfo()) 
```

Adding all services based on roles.

``` python 
for role in config['services']['MGMT']['roles']:
    if not len(mgmt_service.get_roles_by_type(role['group'])) > 0:
        logging.info("Creating role for {0}".format(role['group']))
        mgmt_service.create_role('{0}-1'.format(role['group']), role['group'], role['hosts'][0])
```

Update configuration

``` python
for role in config['services']['MGMT']['roles']:
    role_group = mgmt_service.get_role_config_group('mgmt-{0}-BASE'.format(role['group']))
    logging.info(role_group)
    #
    # Update the group's configuration.
    # [https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.role_config_groups.ApiRoleConfigGroup-class.html#update_config]
    #
    role_group.update_config(role.get('config', {}))
```

Now we start the service.

``` python
#
# Start mgmt services.
#
mgmt_service.start().wait()
```

### Yaml File

<script src="https://gist.github.com/ahmedzbyr/42d02005b2b434138b3cc4c0ae905cf8.js"></script>

### Code File

<script src="https://gist.github.com/ahmedzbyr/d0658e427deb20bd9e0772808ac71085.js"></script>


### Executing Code.

[Video - Setting Up Cloudera Manager Services Using Cloudera API](https://youtu.be/kH1DhfQuD5M)


### Useful Links.

- [Ansible Hadoop Playbook](https://github.com/objectrocket/ansible-hadoop)
- [Cloudera API Example](https://github.com/cloudera/cm_api/blob/master/python/examples/auto-deploy/deploycloudera.py)
- [Cloudera API](https://cloudera.github.io/cm_api/apidocs/v15/index.html)
- [Cloudera Epy Document](https://cloudera.github.io/cm_api/epydoc/5.10.0/index.html)
- [Cloudera API Getting Started](https://ahmedzbyr.github.io/getting-started-with-cloudera-api/)
- [Cloudera API Properties](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/Cloudera-Manager-Configuration-Properties.html)
- [Cloudera Manager Server Properties](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/cm5config_cmserver.html)
- [Cloudera Manager Service Properties](http://www.cloudera.com/documentation/manager/5-0-x/Cloudera-Manager-Configuration-Properties/cm5config_mgmtservice.html)

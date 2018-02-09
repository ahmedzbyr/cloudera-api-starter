
#
# Importing required modules.
#
import time, sys, yaml, logging, argparse
from cm_api.api_client import ApiResource, ApiException
from cm_api.endpoints.services import ApiServiceSetupInfo
from subprocess import call

def enable_license_for_cm(cloudera_manager):

    try:
        cloudera_license = cloudera_manager.get_license()
        print cloudera_license
    except ApiException:
        cloudera_manager.begin_trial()


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


def deploy_management_server(cloudera_manager, config):

    """
        Deploy management services, below are the list of services created.
            - Activity Monitor
            - Alert Publisher
            - Event Server
            - Host Monitor
            - Reports Manager
            - Service Monitor
    :return:
    """
    logging.info("Deploying Management Server Services")
    try:
        #
        # try to get the current service if already present and running.
        #
        mgmt_service = cloudera_manager.get_service()
        if mgmt_service.serviceState == "STARTED":
            logging.info("MGMT service already created on the server")
            return


    except ApiException:
        #
        # If not then we create a mgmt service.
        #
        logging.info("Creating MGMT server")
        mgmt_service = cloudera_manager.create_mgmt_service(ApiServiceSetupInfo())

    #
    # Now add all services to the if not already present
    #
    for role in config['services']['MGMT']['roles']:
        if not len(mgmt_service.get_roles_by_type(role['group'])) > 0:
            logging.info("Creating role for {0}".format(role['group']))
            mgmt_service.create_role('{0}-1'.format(role['group']), role['group'], role['hosts'][0])

    #
    # Update configuration for each service.
    #
    for role in config['services']['MGMT']['roles']:
        role_group = mgmt_service.get_role_config_group('mgmt-{0}-BASE'.format(role['group']))
        logging.info(role_group)
        #
        # Update the group's configuration.
        # [https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.role_config_groups.ApiRoleConfigGroup-class.html#update_config]
        #
        role_group.update_config(role.get('config', {}))

    #
    # Start mgmt services.
    #
    mgmt_service.start().wait()

    #
    # Wait and restart mgmt service just to make sure.
    #
    logging.info("Waiting for MGMT service to restart. !!!")

    #
    # Check for mgmt service, if started, else bail out.
    #
    if cloudera_manager.get_service().serviceState == 'STARTED':
        logging.info("Management Services started")
    else:
        logging.ERROR("[MGMT] Cloudera Management services didn't start up properly")


def deploy_parcels(cloudera_manager, cluster, config):
    """
        Getting parcel and deploying them to all nodes.
    :return:
    """
    logging.info("Setting up parcels")

    # Download Parcel.
    for parcel_config in config['parcels']:
        parcel_download(cloudera_manager, cluster,  parcel_config.get('version'), parcel_config.get('repo'),
                             parcel_config.get('product', 'CDH'))


def parcel_download(cloudera_manager, cluster, version, repo, product):
    """
        Download parcels
    :param version: version to download
    :param repo: Repo details
    :param product: Product name to download CDH, KAFKA
    :return:
    """
    if repo is not None:
        #
        # Get complete configuration and update REMOTE parcel if we dont see it.
        # NOTE : We are already doing this but thats OK :) - `JUST IN CASE`
        #
        cm_config = cloudera_manager.get_config(view='full')
        repo_config = cm_config['REMOTE_PARCEL_REPO_URLS']
        value = ','.join([repo_config.value or repo_config.default, repo])
        cloudera_manager.update_config({'REMOTE_PARCEL_REPO_URLS': value})

    #
    # Star Download and monitor the progress.
    # More Details here : https://cloudera.github.io/cm_api/apidocs/v14/path__clusters_-clusterName-_parcels_products_-product-_versions_-version-.html
    #

    parcel_download = cluster.get_parcel(product, version)
    parcel_download.start_download()

    #
    # We will not check current status of the download.
    # This is a command api.parcel response
    # More details here : https://cloudera.github.io/cm_api/apidocs/v14/ns0_apiParcel.html
    #
    parcel_download = cluster.get_parcel(product, version)
    logging.info("Parcel Downloading: " + str(parcel_download.stage))
    check_current_state(cluster, product, version, ['DOWNLOADED', 'DISTRIBUTED', 'ACTIVATED', 'INUSE'])

    #
    # Now we distribute
    #
    logging.info("Downloaded %s" % (product))
    parcel_distribute(cluster, product, version)


def parcel_distribute(cluster, product, version):
    """

    :param product: product information CDH, KAFKA
    :param version: product version
    :return:
    """

    #
    # Get parcel and distribute it.
    # `start_distribution` is a _cmd execution 'startDistribution'
    # More details _cmd execute here : https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.types.BaseApiResource-class.html#_cmd
    #
    parcel_distribute = cluster.get_parcel(product, version)
    parcel_distribute.start_distribution()

    #
    # check progress for distribution.
    #
    parcel_distribute = cluster.get_parcel(product, version)
    logging.info("Parcel Distribute: " + str(parcel_distribute.stage))
    check_current_state(cluster, product, version, ['DISTRIBUTED', 'ACTIVATED', 'INUSE'])

    #
    # Activating Parcels.
    #
    logging.info("Distributed %s" % (product))
    parcel_activation(cluster, product, version)


def parcel_activation(cluster, product, version):
    """
        Activating parcel.
    :param product: Product info
    :param version: Version
    :return:
    """

    #
    # Activating parcel - using _cmd('activate')
    #
    parcel_activate = cluster.get_parcel(product, version)
    parcel_activate.activate()

    #
    # Checking for progress.
    #
    parcel_activate = cluster.get_parcel(product, version)
    logging.info("Parcel Activation: " + str(parcel_activate.stage))
    check_current_state(cluster, product, version, ['ACTIVATED', 'INUSE'])
    logging.info("Activated %s" % (product))

def check_current_state(cluster, product, version, states):
    """
        Checking status of the command
    :param product:
    :param version:
    :param states:
    :return:
    """

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



def init_cluster(cm_api_handle):
    try:
        cluster = cm_api_handle.get_cluster(config['cluster']['name'])
        return cluster
    except ApiException:
        cluster = cm_api_handle.create_cluster(config['cluster']['name'],
                                                config['cluster']['version'],
                                                config['cluster']['fullVersion'])

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


def create_service(cluster, service_to_create):
    try:
        service = cluster.get_service(service_to_create)
        logging.debug("Service already present on the cluster")
    except ApiException:
        #
        # Create service if it the first time.
        #
        service = cluster.create_service(service_to_create, service_to_create)
        logging.info("Created New Service: " + str(service_to_create))

    return service

def service_update_configuration(service, service_to_update):
    """
        Update service configurations
    :return:
    """
    service.update_config(config['services'][service_to_update]['config'])
    logging.info("Service Configuration Updated.")

def zk_create_cluster_service(config, zk_service):
    #
    # Host Zookeeper ID
    #
    zookeeper_host_id = 0

    #
    # Configure all the host.
    #
    for zookeeper_host in config['services']['ZOOKEEPER']['roles'][0]['hosts']:
        zookeeper_host_id += 1
        zookeeper_role_config = config['services']['ZOOKEEPER']['roles'][0]['config']
        role_name = "{0}-{1}-{2}".format('ZOOKEEPER', 'SERVER', zookeeper_host_id)
        try:
            #
            # Check if role is already present
            #
            role = zk_service.get_role(role_name)
            logging.info("{0} Already Created".format('ZOOKEEPER'))
        except ApiException:
            #
            # Create a role if it is not present and return role.
            #
            role = zk_service.create_role(role_name, 'SERVER', zookeeper_host)
            logging.info("{0} Created on {1} Node".format('ZOOKEEPER', zookeeper_host))

        #
        # Configuring Zookeeper server ID
        #
        zookeeper_role_config['serverId'] = zookeeper_host_id

        #
        # Update configuration
        #
        role.update_config(zookeeper_role_config)
        logging.info(
            "Updated Configuration serverId : {0} , on server {1}".format(zookeeper_host_id, zookeeper_host))


def zk_init_service(zk_service):
    try:
        #
        # Init Zookeeper.
        # Initialize a ZooKeeper service or roles.
        # If no server role names are provided, the command applies to the whole service,
        #   and initializes all the configured server roles.
        #
        # https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.services.ApiService-class.html#init_zookeeper
        #
        zk_init = zk_service.init_zookeeper().wait()
        logging.info("Initializing Zookeeper - Waiting for 15sec...")
        logging.info(str(zk_init))
        time.sleep(15)

    except ApiException:
        logging.info("Already Initialized" + str(ApiException.message))


def started(zk_service):
    if zk_service.serviceState == 'STARTED':
        for role in zk_service.get_all_roles():
            if role.type != 'GATEWAY' and role.roleState != 'STARTED':
                return False
        return True
    return False

def service_starter(service_to_start):
    """
        Service Starter.
        This method does couple of things.
        1. Check if the service is alreadt started.
        2. If not start it and wait till it starts.
        3. Check if the service started successfully.
    :return:
    """


    #
    # Check if the service is already started
    #
    if not started(service_to_start):
        #
        # If not then start it.
        #
        cmd = service_to_start.start()
        logging.debug("Command Response: " + str(cmd))

        #
        # Wait for the service to start up completely.
        #
        if not cmd.wait(300).success:
            logging.info("Command Service start failed. {0}".format(cmd.resultMessage))
            if (cmd.resultMessage is not None and
                        'There is already a pending command on this entity' in cmd.resultMessage):

                #
                # Retry if we can.
                #
                if cmd.canRetry():
                    service_starter(service_to_start)
            raise Exception("Service failed to start")

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

def creating_hdfs_tmp(service):
    """
        Create tmp directory in HDFS.
    :param timeout: seconds to timeout the command
    :param retry: retry executing command if possible.
    :return:
    """

    logging.info("Creating HDFS /tmp Directory.")
    try:
        cmd = service.create_hdfs_tmp()
        logging.debug("Command Response: " + str(cmd))
        if not cmd.wait(300).success:
            if (cmd.resultMessage is not None and
                        "is not currently available for execution" in cmd.resultMessage):
                time.sleep(15)
                if cmd.canRetry():
                    creating_hdfs_tmp()
    except ApiException:
        logging.error("Failed to create tmp in HDFS - " + ApiException.message)


def zookeeper_to_cluster(cluster, config):
    zk_service = create_service(cluster, 'ZOOKEEPER')
    service_update_configuration(zk_service, 'ZOOKEEPER')
    zk_create_cluster_service(config, zk_service)
    zk_init_service(zk_service)
    service_starter(zk_service)

def hdfs_to_cluster(cluster, config):
    hdfs_service = create_service(cluster, 'HDFS')
    service_update_configuration(hdfs_service, 'HDFS')
    hdfs_create_cluster_services(config, hdfs_service, 'HDFS')
    format_namenode(hdfs_service, "NAMENODE")
    service_starter(hdfs_service)
    creating_hdfs_tmp(hdfs_service)


if __name__ == '__main__':

    # setting logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    try:
        with open('cloudera_hdfs.yaml', 'r') as cluster_yaml:
            config = yaml.load(cluster_yaml)

        api_handle = ApiResource(config['cm']['host'],
                                 config['cm']['port'],
                                 config['cm']['username'],
                                 config['cm']['password'],
                                 config['cm']['tls'],
                                 version=config['cm']['api-version'])

        # Checking CM services
        cloudera_manager = api_handle.get_cloudera_manager()

        # Enable License
        enable_license_for_cm(cloudera_manager)

        # Install Hosts
        host_installation(cloudera_manager, config)

        # Init Cluster.
        cluster = init_cluster(api_handle)

        # Deploy Management Services
        deploy_management_server(cloudera_manager, config)


        # Init Cluster.
        deploy_parcels(cloudera_manager, cluster, config)

        # Setting up Zookeeper Service
        zookeeper_to_cluster(cluster, config)
        hdfs_to_cluster(cluster, config)

    except IOError as e:
        logging.error("ERROR {0}. EXIT NOW :( !!!!".format(e))
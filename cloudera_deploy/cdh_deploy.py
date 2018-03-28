#
# Importing required modules.
#
import time, sys, yaml, logging, argparse
from cm_api.api_client import ApiResource, ApiException
import re
import os
from functools import wraps
from cm_api.endpoints.services import ApiServiceSetupInfo, ApiBulkCommandList


def retry(exception_to_check=ApiException, tries=4, delay=3, backoff=2, logger=None):
    """Retry calling the decorated function using an exponential backoff.

    http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param exception_to_check: the exception to check. may be a tuple of
        exceptions to check
    :type exception_to_check: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay each retry
    :type backoff: int
    :param logger: logger to use. If None, print
    :type logger: logging.Logger instance
    """

    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exception_to_check, e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logging.warning(msg)
                    else:
                        print msg
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry


@retry(ApiException, tries=3, delay=30, backoff=1, logger=True)
def execute_cmd(func, service_name, timeout, fail_msg, *args, **kwargs):
    """
    Wrap retry checks for pre and post start commands that sometimes are not available to
    execute immediately after configuring or starting a service
    https://github.com/objectrocket/ansible-hadoop
    """

    def check(cmd, name, fail_msg, timeout, retry=True):
        if not cmd.wait(timeout).success:
            if retry:
                if (cmd.resultMessage is not None and
                        "is not currently available for execution" in cmd.resultMessage):
                    raise ApiException('Retry command')
            logging.error("{}. {}".format(fail_msg, cmd.resultMessage))

    cmd = func(*args, **kwargs)
    if isinstance(cmd, ApiBulkCommandList):
        for cmdi in cmd:
            check(cmdi, service_name, fail_msg, timeout, retry=False)
    else:
        check(cmd, service_name, fail_msg, timeout)


class ClouderaManagerSetup(object):

    def __init__(self, config, trial_version=True, license_information=None):
        """
            Getting the Core Ready
        :param config:
        :param trial_version:
        :param license_information:
        """
        self.config = config
        self.cluster = {}
        self.trial = trial_version
        self.license_information = license_information
        self._api_resource = None
        self._cloudera_manager_handle = None

    def __getitem__(self, item):
        return getattr(self, item)

    @property
    def api_resource(self):
        """
            Get the API resource
        :return:
        """
        if self._api_resource is None:
            self._api_resource = ApiResource(self.config['cloudera_manager']['authentication']['host'],
                                             self.config['cloudera_manager']['authentication']['port'],
                                             self.config['cloudera_manager']['authentication']['username'],
                                             self.config['cloudera_manager']['authentication']['password'],
                                             self.config['cloudera_manager']['authentication']['tls'],
                                             version=self.config['cloudera_manager']['authentication']['api-version'])

        return self._api_resource

    @property
    def cloudera_manager_handle(self):
        """
            Get CM Handle
        :return:
        """
        if self._cloudera_manager_handle is None:
            self._cloudera_manager_handle = self.api_resource.get_cloudera_manager()
        return self._cloudera_manager_handle

    def enable_trial_license_for_cm(self):
        """
            Setting TRIAL version by default
        :return:
        """
        try:
            cloudera_license = self.cloudera_manager_handle.get_license()
            logging.debug("Currently Lic Information: " + str(cloudera_license))
        except ApiException:
            self.cloudera_manager_handle.begin_trial()

    def update_adv_cm_config(self):
        """
            Update Advance Configuration on Cloudera Manager.
        :return:
        """
        self.cloudera_manager_handle.update_config(self.config['cloudera_manager']['cm_advance_config'])

    def host_installation(self):
        """
            Host installation.
            https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.cms.ClouderaManager-class.html#host_install
        """

        for nodes_in_cluster in self.config['clusters']:

            logging.info("Installing HOSTs.")
            cmd = self.cloudera_manager_handle.host_install(
                self.config['host_installation']['authentication']['host_username'],
                nodes_in_cluster['hosts'],
                ssh_port=self.config['host_installation']['authentication']['host_ssh_port'],
                private_key=self.config['host_installation']['authentication']['host_private_key'],
                parallel_install_count=self.config['host_installation']['authentication'][
                    'host_parallel_install_count'],
                cm_repo_url=self.config['host_installation']['authentication']['host_cm_repo_url'],
                gpg_key_custom_url=self.config['host_installation']['authentication'][
                    'host_cm_repo_gpg_key_custom_url'],
                java_install_strategy=self.config['host_installation']['authentication']['host_java_install_strategy'],
                unlimited_jce=self.config['host_installation']['authentication']['host_unlimited_jce_policy'])

            #
            # Check command to complete.
            #
            if not cmd.wait().success:
                logging.info("Command `host_install` FAILED. {0} - EXITING NOW".format(cmd.resultMessage))
                if (cmd.resultMessage is not None and
                        'There is already a pending command on this entity' in cmd.resultMessage):
                    raise Exception("HOST INSTALLATION FAILED.")

                exit()

    def deploy_cloudera_management_services(self):

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
            mgmt_service = self.cloudera_manager_handle.get_service()
            if mgmt_service.serviceState == "STARTED":
                logging.info("MGMT service already created on the server")
                return

        except ApiException:
            #
            # If not then we create a mgmt service.
            #
            logging.info("Creating MGMT server")
            mgmt_service = self.cloudera_manager_handle.create_mgmt_service(ApiServiceSetupInfo())

        #
        # Now add all services to the if not already present
        #
        for role in config['cloudera_manager']['mgmt_services']['MGMT']['roles']:
            if not len(mgmt_service.get_roles_by_type(role['group'])) > 0:
                logging.info("Creating role for {0} {1}".format(role['group'], role['hosts'][0]))
                mgmt_service.create_role('{0}-1'.format(role['group']), role['group'], role['hosts'][0])

        #
        # Update configuration for each service.
        #
        for role in config['cloudera_manager']['mgmt_services']['MGMT']['roles']:
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
        if self.cloudera_manager_handle.get_service().serviceState == 'STARTED':
            logging.info("Management Services started")
        else:
            logging.ERROR("[MGMT] Cloudera Management services didn't start up properly")

    def setup_cdh_manager(self):
        """
            Core Method to run the rest of the methods.
        :return:
        """
        self.enable_trial_license_for_cm()
        self.update_adv_cm_config()

        # Currently commented as we are setting this up using Chef, but we can enable it as required.
        # self.host_installation()
        self.deploy_cloudera_management_services()


class ParcelsSetup(object):

    def __init__(self, cluster_to_deploy, parcel_version, parcel_name='CDH'):
        """
            Parcel Setup.
        :param cluster_to_deploy:
        :param parcel_version:
        :param parcel_name:
        """
        self.cluster_to_deploy = cluster_to_deploy
        self.parcel_version = parcel_version
        self.parcel_name = parcel_name

    @property
    def parcel(self):
        #
        # Returns https://cloudera.github.io/cm_api/apidocs/v15/ns0_apiParcel.html
        #
        return self.cluster_to_deploy.get_parcel(self.parcel_name, self.parcel_version)

    def check_for_parcel_error(self):
        """
            Check we have any errors on parcels.
        :return:
        """
        if self.parcel.state.errors:
            logging.error(self.parcel.state.errors)
            sys.exit(1)

    def check_parcel_availability(self):
        """
            Check AVAIL Parcels. This will use the Advance CM configuration from the YAML.
        :return:
        """
        logging.debug("Current State:" + str(self.parcel.stage))
        if self.parcel.stage in ['AVAILABLE_REMOTELY', 'DOWNLOADED', 'DOWNLOADING',
                                 'DISTRIBUTING', 'DISTRIBUTED', 'ACTIVATING', 'ACTIVATED']:
            logging.info("Parcel is AVAILABLE, we can proceed")
        else:
            logging.error("Parcel NOT AVAILABLE, Exit Now. Check Parcel Version and Name")
            sys.exit(1)

    @retry(ApiException, tries=60, delay=10, backoff=1, logger=True)
    def check_parcel_state(self, current_state):
        """
            Retry and check the current state.
        :param current_state:
        :return:
        """
        parcel = self.parcel
        self.check_for_parcel_error()
        if parcel.stage in current_state:
            return
        else:
            logging.info("{} progress: {} / {}".format(current_state[0], parcel.state.progress,
                                                       parcel.state.totalProgress))
            raise ApiException("Waiting for {}".format(current_state[0]))

    def parcel_download(self):
        """
            Download
        :return:
        """
        self.check_parcel_availability()
        self.parcel.start_download()
        self.check_parcel_state(['DOWNLOADED', 'DISTRIBUTED', 'ACTIVATED', 'INUSE'])

    def parcel_distribute(self):
        """
            Distribute
        :return:
        """
        self.parcel.start_distribution()
        self.check_parcel_state(['DISTRIBUTED', 'ACTIVATED', 'INUSE'])

    def parcel_activate(self):
        """
            Activate
        :return:
        """
        self.parcel.activate()
        self.check_parcel_state(['ACTIVATED', 'INUSE'])


class Clusters(ClouderaManagerSetup):

    def init_cluster(self):
        """
            INIT Clusters
        :return:
        """
        logging.debug(config['clusters'])
        for cluster_to_init in config['clusters']:
            self.initialize(cluster_to_init)

    def initialize(self, cluster_config):
        """
            Init Each cluster in the YAML
        :param cluster_config:
        :return:
        """
        logging.debug(cluster_config['cluster'])
        try:

            self.cluster[cluster_config['cluster']] = self.api_resource.get_cluster(cluster_config['cluster'])
            logging.debug("Cluster Already Exists:" + str(self.cluster))
            return

        except ApiException:
            self.cluster[cluster_config['cluster']] = self.api_resource.create_cluster(cluster_config['cluster'],
                                                                                       cluster_config['version'],
                                                                                       cluster_config['fullVersion'])

            logging.debug("Cluster Created:" + str(self.cluster))

        cluster_hosts = [self.api_resource.get_host(host.hostId).hostname
                         for host in self.cluster[cluster_config['cluster']].list_hosts()]
        logging.info('Nodes already in Cluster: ' + str(cluster_hosts))

        #
        # New hosts to be added to the cluster..
        #
        hosts = []

        #
        # Create a host list, make sure we dont have duplicates.
        #
        for host in cluster_config['hosts']:
            if host not in cluster_hosts:
                hosts.append(host)

        logging.info("Adding new nodes:" + str(hosts))

        #
        # Adding all hosts to the cluster.
        #
        try:
            self.cluster[cluster_config['cluster']].rename(cluster_config['cluster_display_name'])
            self.cluster[cluster_config['cluster']].add_hosts(hosts)
        except ApiException:
            logging.error(
                "Cannot `add_hosts`, Please check if one or more of the hosts are NOT already part of an existing cluster.")
            sys.exit(1)

    def activate_parcels_all_cluster(self):
        """
            Activating all Parcels for all Clusters.
        :return:
        """
        for cluster_to_deploy in config['clusters']:
            logging.debug(cluster_to_deploy)
            for parcel_cfg in cluster_to_deploy['parcels']:
                parcel = ParcelsSetup(self.cluster[cluster_to_deploy['cluster']], parcel_cfg.get('version'),
                                      parcel_cfg.get('product', 'CDH'))
                parcel.parcel_download()
                parcel.parcel_distribute()
                parcel.parcel_activate()

    @retry(ApiException, tries=3, delay=10, backoff=1, logger=True)
    def cluster_deploy_client_config(self, cluster_to_deploy):
        """
            Deploy Client Config
        :param cluster_to_deploy:
        :return:
        """
        command = cluster_to_deploy.deploy_client_config()
        if not command.wait(300).success:
            if command.resultMessage is not None and \
                    'There is already a pending command on this entity' in command.resultMessage:
                raise ApiException('Retry Command')
            if 'is not currently available for execution' in command.resultMessage:
                raise ApiException('Retry Command')

    def deploy_services_on_cluster(self):
        """
            Deploy all services on all clustes using the BASE_HADOOP_SERVICES macro.
        :return:
        """
        for cluster_to_deploy in config['clusters']:
            #
            #   Adding the services from the YAML file.
            #
            for cluster_services in cluster_to_deploy['services_to_install']:
                svc = getattr(sys.modules[__name__], cluster_services.capitalize())(
                    self.cluster[cluster_to_deploy['cluster']],
                    cluster_to_deploy['services'][cluster_services.upper()], cluster_to_deploy['cluster'])
                if not svc.check_service_start:
                    svc.deploy_service()
                    svc.pre_start_configuration()

            try:
                self.cluster_deploy_client_config(self.cluster[cluster_to_deploy['cluster']])
            except ApiException:
                pass

            for cluster_services in cluster_to_deploy['services_to_install']:
                svc = getattr(sys.modules[__name__], cluster_services)(self.cluster[cluster_to_deploy['cluster']],
                                                                       cluster_to_deploy['services'][
                                                                           cluster_services.upper()],
                                                                       cluster_to_deploy['cluster'])
                if not svc.check_service_start:
                    svc.service_start()
                    svc.post_start_configuration()

    def setup(self):
        """
            Setup the CLUSTERS
        :return:
        """
        self.init_cluster()
        self.activate_parcels_all_cluster()
        self.deploy_services_on_cluster()


class CoreServices(object):

    def __init__(self, cluster_to_deploy, service_config, cluster_name):
        """
            Setting up the common services
        :param cluster_to_deploy:
        :param service_config:
        :param cluster_name:
        """
        self.cluster_to_deploy = cluster_to_deploy
        self.service_config = service_config
        self.cluster_name = cluster_name
        self._service = None

    @property
    def service_type(self):
        return self.__class__.__name__.upper()

    @property
    def service_name(self):
        return self.service_type + '-' + str(self.cluster_name)

    @property
    def service(self):
        if self._service is not None:
            return self._service
        try:
            self._service = self.cluster_to_deploy.get_service(self.service_name)
            logging.debug("Service {0} already present on the cluster".format(self.service_name))
        except ApiException:
            self._service = self.cluster_to_deploy.create_service(self.service_name, self.service_type)
            logging.debug("Service {0} created on cluster".format(self.service_name))
        return self._service

    @property
    def check_service_start(self):
        if self.service.serviceState == 'STARTED':
            for role in self.service.get_all_roles():
                if role.type != 'GATEWAY' and role.roleState != 'STARTED':
                    return False
            return True
        return False

    def run_cmd(self, func, timeout, fail_msg, *args, **kwargs):
        """
        :param func: Function to execute
        :param timeout: Timeout for the function
        :param fail_msg: Failure message to display if the function fails
        :param args: Further args are required
        :param kwargs:
        :return:
        """
        execute_cmd(func, self.service_name, timeout, fail_msg, *args, **kwargs)

    def deploy_service(self):
        """
        Update group configs. Create roles and update role specific configs.
        """

        # Service creation and config updates
        self.service.update_config(self.service_config.get('config', {}))

        # Retrieve base role config groups, update configs for those and create individual roles
        # per host
        if not self.service_config.get('roles'):
            raise Exception("[{}] Atleast one role should be specified per service".format(self.service_name))
        for role in self.service_config['roles']:
            if not role.get('group') and role.get('hosts'):
                raise Exception("[{}] group and hosts should be specified per role".format(self.service_name))
            group = role['group']
            role_group = self.service.get_role_config_group('{}-{}-BASE'.format(self.service_name, group))
            role_group.update_config(role.get('config', {}))
            self.create_roles(role, group)

    @retry(ApiException, tries=3, delay=30, backoff=2, logger=True)
    def service_start(self):
        """
            Starting Service
        :return:
        """
        # setting the private place holder to None
        self._service = None
        if not self.check_service_start:
            command = self.service.start()
            if not command.wait(300).success:
                if command.resultMessage is not None and \
                        'There is already a pending command on this entity' in command.resultMessage:
                    raise ApiException('Retry Command')
                if command.resultMessage is not None and \
                        'Command Start is not currently available for execution' in command.resultMessage:
                    raise ApiException('Retry Command')
                raise Exception("Service {} FAILED to Start".format(self.service_name))
        # Making sure the place holder is None
        self._service = None

    def create_roles(self, role, group):
        """
            Creating ROLES.
        :param role:
        :param group:
        :return:
        """
        role_suffix = 0
        for host in role.get('hosts', []):
            role_suffix += 1

            #
            # When specifying roles to be created, the names provided for each role
            # 	must not conflict with the names that CM auto-generates for roles.
            # 	Specifically, names of the form "<service name>-<role type>-<arbitrary value>" cannot be used unless the
            # 	<arbitrary value> is the same one CM would use. If CM detects such a
            # 	conflict, the error message will indicate what <arbitrary value> is safe to use.
            #
            #	Alternately, a differently formatted name should be used.
            #

            role_name = '{}_{}_{}'.format(self.service_name, group, role_suffix)
            logging.debug("Role name:" + role_name)
            try:
                self.service.get_role(role_name)
            except ApiException:
                self.service.create_role(role_name, group, host)

    def pre_start_configuration(self):
        """
            Any services which require this will implement it in its own class.
            As this will be different for each service.
        """
        pass

    def post_start_configuration(self):
        """
            Any services which require this will implement it in its own class.
            As this will be different for each service.
        """
        pass


class Zookeeper(CoreServices):

    def create_roles(self, role, group):
        """
            Creating Roles for zookeeper,
            this is a little different for Zookeeper as we need to have id for each server.
        :param role:
        :param group:
        :return:
        """
        role_suffix = 0
        for host in role['hosts']:
            role_suffix += 1

            #
            # When specifying roles to be created, the names provided for each role
            # 	must not conflict with the names that CM auto-generates for roles.
            # 	Specifically, names of the form "<service name>-<role type>-<arbitrary value>" cannot be used unless the
            # 	<arbitrary value> is the same one CM would use. If CM detects such a
            # 	conflict, the error message will indicate what <arbitrary value> is safe to use.
            #
            #	Alternately, a differently formatted name should be used.
            #

            role_name = '{}_{}_{}'.format(self.service_name, group, role_suffix)
            logging.debug("Role name:" + role_name)
            try:
                role = self.service.get_role(role_name)
            except ApiException:
                role = self.service.create_role(role_name, group, host)
            role.update_config({'serverId': role_suffix})

    def pre_start_configuration(self):
        """
            Pre Start configuration to init the zookeeper.
        """
        self.run_cmd(self.service.init_zookeeper, 30, 'Init Zookeeper FAILED.')


class Kafka(CoreServices):
    """
        Service Role Groups: Nothing to do here as this is same as the core services.
        Further configuration will come from the YAML file.
        KAFKA_BROKER

        We can further add MIRROR_MAKER and GATEWAY from the YAML file.
        All we need to do is add the configuration in the YAML file.

        Kafka Service
    """


class Hdfs(CoreServices):

    @property
    def active_namenode(self):
        return '{}_NAMENODE_1'.format(self.service_name)

    @property
    def standby_namenode(self):
        return '{}_NAMENODE_2'.format(self.service_name)

    @property
    def failover_primary(self):
        return '{}_FAILOVERCONTROLLER_1'.format(self.service_name)

    @property
    def failover_secondary(self):
        return '{}_FAILOVERCONTROLLER_2'.format(self.service_name)

    @property
    def ha(self):
        try:
            self.service.get_role('SECONDARYNAMENODE')
            return False
        except ApiException:
            return True

    def format_namenode(self):
        self.run_cmd(self.service.format_hdfs, 300, "FAILED formatting HDFS, Continuing ...", self.active_namenode)

    def pre_start_configuration(self):
        if not self.ha:
            self.format_namenode()
            return

        self.run_cmd(self.service.init_hdfs_auto_failover, 300, "FAILED setup FO Controller", self.failover_primary)
        roles = [role.name for role in self.service.get_roles_by_type('JOURNALNODE')]
        self.run_cmd(self.service.start_roles, 300, "Service start FAILED", *roles)
        self.format_namenode()
        self.run_cmd(self.service.start_roles, 300, "Service start FAILED", self.active_namenode)
        self.run_cmd(self.service.bootstrap_hdfs_stand_by, 300, "Bootstrap Standby NN FAILED", self.standby_namenode)
        self.run_cmd(self.service.start_roles, 300, "Service start FAILED", self.standby_namenode)
        self.run_cmd(self.service.start_roles, 300, "Service start FAILED", self.failover_primary)
        self.run_cmd(self.service.start_roles, 300, "Service start FAILED", self.failover_secondary)

    def post_start_configuration(self):
        self.run_cmd(self.service.create_hdfs_tmp, 60, "Command CreateHdfsTmp FAILED")


class Yarn(CoreServices):
    def pre_start_configuration(self):
        self.run_cmd(self.service.create_yarn_job_history_dir, 60, "Command Create Job History Dir failed")
        self.run_cmd(self.service.create_yarn_node_manager_remote_app_log_dir, 60, "Command Create NodeManager app dir failed")


class Spark_On_Yarn(CoreServices):
    def pre_start_configuration(self):
        self.run_cmd(self.service._cmd, 60, "Cmd CreateSparkUserDir failed", 'CreateSparkUserDirCommand', api_version=7)
        self.run_cmd(self.service._cmd, 60, "Cmd CreateSparkHistoryDirCommand failed", 'CreateSparkHistoryDirCommand', api_version=7)
        self.run_cmd(self.service._cmd, 60, "Cmd SparkUploadJarServiceCommand failed", 'SparkUploadJarServiceCommand', api_version=7)


class Hbase(CoreServices):
    def pre_start_configuration(self):
        self.run_cmd(self.service.create_hbase_root, 60, "Command CreateHbaseRoot failed")


class Hive(CoreServices):
    def pre_start_configuration(self):
        self.run_cmd(self.service.create_hive_warehouse, 60, "Command CreateHiveWarehouse failed")
        self.run_cmd(self.service.create_hive_metastore_database, 60, "Command CreateHiveMetastoreDatabase failed")
        self.run_cmd(self.service.create_hive_metastore_tables, 60, "Command CreateHiveMetastoreTables failed")


class Impala(CoreServices):
    def pre_start_configuration(self):
        self.run_cmd(self.service.create_impala_user_dir, 60, "Command CreateImpalaUserDir failed")


class Flume(CoreServices):
    """
        Service Role Groups: Nothing to do here as this is same as the core services.
        Further configuration will come from the YAML file.

        Flume service
    """

class Hue(CoreServices):
    """
        Service Role Groups: Nothing to do here as this is same as the core services.
        Further configuration will come from the YAML file.

        Hue Service
    """

class Oozie(CoreServices):
    def pre_start_configuration(self):
        self.run_cmd(self.service.create_oozie_db, 300, "Command CreateOozieSchema failed")
        self.run_cmd(self.service.install_oozie_sharelib, 300, "Command InstallOozieSharedLib failed")


class Sqoop(CoreServices):
    def pre_start_configuration(self):
        self.run_cmd(self.service.create_sqoop_user_dir, 300, "Command CreateSqoopUserDir failed")
        self.run_cmd(self.service.create_sqoop_database_tables, 300, "Command CreateSqoopDBTables failed")


class Solr(CoreServices):
    def pre_start_configuration(self):
        self.run_cmd(self.service.init_solr, 300, "Command InitSolr failed")
        self.run_cmd(self.service.create_solr_hdfs_home_dir, 300, "Command CreateSolrHdfsHomeDir failed")


class Sentry(CoreServices):
    def pre_start_configuration(self):
        self.run_cmd(self.service.create_sentry_database_tables, 300, "Command CreateSentryDBTables failed")

if __name__ == '__main__':

    command_line_opt = argparse.ArgumentParser("Setting up cloudera cluster using automation script.")
    command_line_opt.add_argument('-f', '--file', help='YAML configuration file for auto deployment.', required=True)
    command_line_opt.add_argument('-d', '--debug', help='Running debug mode.', action="store_true")
    command_line_opt.add_argument('-v', '--version', help="Show script version", action="version",
                                  version="CDH Auto Deploy 0.1.0")

    args = command_line_opt.parse_args()
    file_name = args.file

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if not os.path.isfile(file_name):
        logging.error("File Not Present")
        command_line_opt.print_help()

    try:
        with open(file_name, 'r') as cluster_yaml:
            config = yaml.load(cluster_yaml)

        print config
        for item in config['clusters']:
            print item['hosts']

        cloudera_manager = ClouderaManagerSetup(config)
        cloudera_manager.setup_cdh_manager()

        cluster = Clusters(config)
        cluster.setup()

    except IOError as e:
        logging.error("ERROR {0}. EXIT NOW :( !!!!".format(e))

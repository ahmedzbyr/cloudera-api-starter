
#
# Importing required modules.
#
import time, sys, yaml, logging, argparse
from cm_api.api_client import ApiResource, ApiException
from cm_api.endpoints.services import ApiServiceSetupInfo
import os
from functools import wraps

BASE_HADOOP_SERVICES = ['Zookeeper']

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


class ClouderaManagerSetup(object):

    def __init__(self, config, trial_version=True, license_information=None):
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
        if self._cloudera_manager_handle is None:
            self._cloudera_manager_handle = self.api_resource.get_cloudera_manager()
        return  self._cloudera_manager_handle

    def enable_trial_license_for_cm(self):

        try:
            cloudera_license = self.cloudera_manager_handle.get_license()
            logging.debug("Currently Lic Information: " + str(cloudera_license))
        except ApiException:
            self.cloudera_manager_handle.begin_trial()

    def update_adv_cm_config(self):
        self.cloudera_manager_handle.update_config(self.config['cloudera_manager']['cm_advance_config'])

    def host_installation(self):
        """
            Host installation.
            https://cloudera.github.io/cm_api/epydoc/5.10.0/cm_api.endpoints.cms.ClouderaManager-class.html#host_install
        """

        for nodes_in_cluster in self.config['clusters']:

            logging.info("Installing HOSTs.")
            cmd = self.cloudera_manager_handle.host_install(self.config['host_installation']['authentication']['host_username'],
                        nodes_in_cluster['hosts'],
                        ssh_port=self.config['host_installation']['authentication']['host_ssh_port'],
                        private_key=self.config['host_installation']['authentication']['host_private_key'],
                        parallel_install_count=self.config['host_installation']['authentication']['host_parallel_install_count'],
                        cm_repo_url=self.config['host_installation']['authentication']['host_cm_repo_url'],
                        gpg_key_custom_url=self.config['host_installation']['authentication']['host_cm_repo_gpg_key_custom_url'],
                        java_install_strategy=self.config['host_installation']['authentication']['host_java_install_strategy'],
                        unlimited_jce=self.config['host_installation']['authentication']['host_unlimited_jce_policy'])

            #
            # Check command to complete.
            #
            if not cmd.wait().success:
                logging.info("Command `host_install` Failed. {0} - EXITING NOW".format(cmd.resultMessage))
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

    def setup(self):
        self.enable_trial_license_for_cm()
        self.update_adv_cm_config()
        #self.host_installation()
        self.deploy_cloudera_management_services()


class ParcelsSetup(object):

    def __init__(self, cluster_to_deploy, parcel_version, parcel_name='CDH'):
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
        if self.parcel.state.errors:
            logging.error(self.parcel.state.errors)
            sys.exit(1)

    def check_parcel_availability (self):
        logging.debug("Current State:" + str(self.parcel.stage))
        if self.parcel.stage in ['AVAILABLE_REMOTELY', 'DOWNLOADED', 'DOWNLOADING',
                                 'DISTRIBUTING', 'DISTRIBUTED', 'ACTIVATING', 'ACTIVATED']:
            logging.info("Parcel is AVAILABLE, we can proceed")
        else:
            logging.error("Parcel NOT AVAILABLE, Exit Now. Check Parcel Version and Name")
            sys.exit(1)

    @retry(ApiException, tries=60, delay=10, backoff=1, logger=True)
    def check_parcel_state(self, current_state):
        parcel = self.parcel
        self.check_for_parcel_error()
        if parcel.stage in current_state:
            return
        else:
            logging.info("{} progress: {} / {}".format(current_state[0], parcel.state.progress,
                                                       parcel.state.totalProgress))
            raise ApiException("Waiting for {}".format(current_state[0]))

    def parcel_download(self):
        self.check_parcel_availability()
        self.parcel.start_download()
        self.check_parcel_state(['DOWNLOADED', 'DISTRIBUTED', 'ACTIVATED', 'INUSE'])

    def parcel_distribute(self):
        self.parcel.start_distribution()
        self.check_parcel_state(['DISTRIBUTED', 'ACTIVATED', 'INUSE'])

    def parcel_activate(self):
        self.parcel.activate()
        self.check_parcel_state(['ACTIVATED', 'INUSE'])


class Clusters(ClouderaManagerSetup):

    def init_cluster(self):

        logging.debug(config['clusters'])
        for cluster_to_init in config['clusters']:
            try:

                self.cluster[cluster_to_init['cluster']] = self.api_resource.get_cluster(cluster_to_init['cluster'])
                logging.debug("Cluster Already Exists:" + str(self.cluster))
                return self.cluster

            except ApiException:
                self.cluster[cluster_to_init['cluster']] = self.api_resource.create_cluster(cluster_to_init['cluster'],
                                                        cluster_to_init['version'],
                                                        cluster_to_init['fullVersion'])

                logging.debug("Cluster Created:" + str(self.cluster))

            cluster_hosts = [self.api_resource.get_host(host.hostId).hostname
                             for host in self.cluster[cluster_to_init['cluster']].list_hosts()]
            logging.info('Nodes already in Cluster: ' + str(cluster_hosts))

            #
            # New hosts to be added to the cluster..
            #
            hosts = []

            #
            # Create a host list, make sure we dont have duplicates.
            #
            for host in cluster_to_init['hosts']:
                if host not in cluster_hosts:
                    hosts.append(host)

            logging.info("Adding new nodes:" + str(hosts))

            #
            # Adding all hosts to the cluster.
            #
            self.cluster[cluster_to_init['cluster']].add_hosts(hosts)

        return self.cluster

    def activate_parcels_all_cluster(self):
        for cluster_to_deploy in config['clusters']:
            for parcel_cfg in cluster_to_deploy['parcels']:
                parcel = ParcelsSetup(self.cluster[cluster_to_deploy['cluster']], parcel_cfg.get('version'),
                                      parcel_cfg.get('product', 'CDH'))
                parcel.parcel_download()
                parcel.parcel_distribute()
                parcel.parcel_activate()

    @retry(ApiException, tries=3, delay=10, backoff=1, logger=True)
    def cluster_deploy_client_config(self, cluster_to_deploy):
        command = cluster_to_deploy.deploy_client_config()
        if not command.wait(300).success:
            if command.resultMessage is not None and \
                    'There is already a pending command on this entity' in command.resultMessage:
                raise ApiException('Retry Command')
            if 'is not currently available for execution' in command.resultMessage:
                raise ApiException('Retry Command')

    def deploy_services_on_cluster(self):
        for cluster_to_deploy in config['clusters']:
            for cluster_services in BASE_HADOOP_SERVICES:
                svc = getattr(sys.modules[__name__], cluster_services.capitalize())(self.cluster[cluster_to_deploy['cluster']],
                                cluster_to_deploy['services'][cluster_services.upper()])
                if not svc.check_service_start:
                    svc.deploy_service()
                    svc.pre_start_configuration()

            try:
                self.cluster_deploy_client_config(self.cluster[cluster_to_deploy['cluster']])
            except ApiException:
                pass

            for cluster_services in BASE_HADOOP_SERVICES:
                svc = getattr(sys.modules[__name__], cluster_services)(self.cluster[cluster_to_deploy['cluster']],
                                cluster_to_deploy['services'][cluster_services.upper()])
                if not svc.check_service_start:
                    svc.service_start()
                    svc.post_start_configuration()


    def setup(self):
        self.init_cluster()
        self.activate_parcels_all_cluster()
        self.deploy_services_on_cluster()


class CoreServices(object):

    def __init__(self, cluster_to_deploy, service_config):
        self.cluster_to_deploy = cluster_to_deploy
        self.service_config = service_config
        self._service = None

    @property
    def service_type(self):
        return self.__class__.__name__.upper()

    @property
    def service_name(self):
        return self.service_type + str('-1')

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
        # setting the private place holder to None
        self._service = None
        if not self.check_service_start:
            command = self.service.start()
            if not command.wait(300).success:
                if command.resultMessage is not None and \
                        'There is already a pending command on this entity' in command.resultMessage:
                    raise ApiException('Retry Command')
                if 'Command Start is not currently available for execution' in command.resultMessage:
                    raise ApiException('Retry Command')
                raise Exception("Service {} Failed to Start".format(self.service_name))
        # Making sure the place holder is None
        self._service = None

    def create_roles(self, role, group):

        role_id = 0
        for host in role.get('hosts', []):
            role_id += 1
            role_name = '{}-{}-{}'.format(self.service_name, group, role_id)
            try:
                self.service.get_role(role_name)
            except ApiException:
                self.service.create_role(role_name, group, host)

    def pre_start_configuration(self):
        """
        Any service specific actions that needs to be performed before the cluster is started.
        Each service subclass can implement and hook into the pre-start process.
        """
        pass

    def post_start_configuration(self):
        """
        Post cluster start actions required to be performed on a per service basis.
        """
        pass


class Zookeeper(CoreServices):
    """
    Service Role Groups:
        SERVER
    """
    def create_roles(self, role, group):
        role_id = 0
        for host in role['hosts']:
            role_id += 1
            role_name = '{}-{}-{}'.format(self.service_type, group, role_id)
            try:
                role = self.service.get_role(role_name)
            except ApiException:
                role = self.service.create_role(role_name, group, host)
            role.update_config({'serverId': role_id})

    @retry(ApiException, tries=3, delay=30, backoff=1, logger=True)
    def pre_start_configuration(self):
        if not self.service_name.init_zookeeper().wait(60).success:
            raise ApiException('Retry Command')
        return


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
        cloudera_manager.setup()

        cluster = Clusters(config)
        cluster.setup()

    except IOError as e:
        logging.error("ERROR {0}. EXIT NOW :( !!!!".format(e))

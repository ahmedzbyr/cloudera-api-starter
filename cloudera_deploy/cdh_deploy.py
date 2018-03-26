
#
# Importing required modules.
#
import time, sys, yaml, logging, argparse
from cm_api.api_client import ApiResource, ApiException
from cm_api.endpoints.services import ApiServiceSetupInfo
import os
from functools import wraps
from subprocess import call



def retry(attempts=3, delay=5):
    """Function which reruns/retries other functions.
    'attempts' - the number of attempted retries (defaults to 3)
    'delay' - time in seconds between each retry (defaults to 5)
    """
    def deco_retry(func):
        """Main decorator function."""
        @wraps(func)
        def retry_loop(*args, **kwargs):
            """Main num_tries loop."""
            attempt_counter = 1
            while attempt_counter <= attempts:
                try:
                    return func(*args, **kwargs)
                except ApiException as apie:  # pylint: disable=broad-except,catching-non-exception
                    if attempt_counter == attempts:
                        # pylint: disable=raising-bad-type
                        raise
                    time.sleep(delay)
                    attempt_counter += 1
        return retry_loop
    return deco_retry


class ClouderaManagerSetup():


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



class ParcelsSetup():

    def __init__(self, cluster_to_deploy, parcel_version, parcel_name='CDH'):
        self.cluster_to_deploy = cluster_to_deploy
        self.parcel_version = parcel_version
        self.parcel_name = parcel_name


    # def get_parcel(self, product, version):
    #     """
    #     Lookup a parcel by product and version.
    #
    #     @param product: the product name
    #     @param version: the product version
    #     @return: An ApiParcel object
    #     """

    @property
    def parcel(self):
        #
        # Returns https://cloudera.github.io/cm_api/apidocs/v15/ns0_apiParcel.html
        #
        return self.cluster_to_deploy.get_parcel(self.parcel_name, self.parcel_version)



    def check_for_parcel_error(self, parcel_state):
        if parcel_state.state.errors:
            logging.error(parcel_state.state.errors)
            sys.exit(1)


    def check_parcel_availability (self):

        logging.debug("Current State:" + str(self.parcel.stage))
        if self.parcel.stage in ['AVAILABLE_REMOTELY', 'DOWNLOADED', 'DOWNLOADING',
                                 'DISTRIBUTING', 'DISTRIBUTED', 'ACTIVATING', 'ACTIVATED']:
            logging.info("Parcel is AVAILABLE, we can proceed")
        else:
            logging.error("Parcel Not AVAILABLE, exiting Now. Check Parcel Version and Name")
            sys.exit(1)


    @retry(attempts=20, delay=30)
    def check_parcel_state(self, current_state):
        parcel = self.parcel
        self.check_for_parcel_error(parcel)
        if parcel.stage in current_state:
            return
        else:
            logging.info("{} progress: {} / {}".format(current_state[0], parcel.state.progress, parcel.state.totalProgress))
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

        for cluster in config['clusters']:
            try:

                self.cluster[cluster['cluster']] = self.api_resource.get_cluster(cluster['cluster'])
                logging.debug("Cluster Already Exists:" + str(self.cluster))
                return self.cluster

            except ApiException:
                self.cluster[cluster['cluster']] = self.api_resource.create_cluster(cluster['cluster'],
                                                        cluster['version'],
                                                        cluster['fullVersion'])


                logging.debug("Cluster Created:" + str(self.cluster))

            cluster_hosts = [self.api_resource.get_host(host.hostId).hostname
                             for host in self.cluster[cluster['cluster']].list_hosts()]
            logging.info('Nodes already in Cluster: ' + str(cluster_hosts))

            #
            # New hosts to be added to the cluster..
            #
            hosts = []

            #
            # Create a host list, make sure we dont have duplicates.
            #
            for host in cluster['hosts']:
                if host not in cluster_hosts:
                    hosts.append(host)


            #
            logging.info("Adding new nodes:" + str(hosts))

            #
            # Adding all hosts to the cluster.
            #
            self.cluster[cluster['cluster']].add_hosts(hosts)


        return self.cluster


    def activate_parcels_all_cluster(self):
        for cluster_to_deploy in config['clusters']:
            for parcel_cfg in cluster_to_deploy['parcels']:
                parcel = ParcelsSetup(self.cluster[cluster_to_deploy['cluster']], parcel_cfg.get('version'),
                                      parcel_cfg.get('product', 'CDH'))
                parcel.parcel_download()
                parcel.parcel_distribute()
                parcel.parcel_activate()


    def setup(self):
        self.init_cluster()
        self.activate_parcels_all_cluster()


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

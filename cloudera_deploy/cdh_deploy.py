
#
# Importing required modules.
#
import time, sys, yaml, logging, argparse
from cm_api.api_client import ApiResource, ApiException
from cm_api.endpoints.services import ApiServiceSetupInfo
import os
from subprocess import call


class ClouderaManagerSetup():


    def __init__(self, config, trial_version=True, license_information=None):
        self.config = config
        self.trial = trial_version
        self.license_information = license_information
        self.cluster = {}
        self._api_resource = None
        self._cloudera_manager_handle = None

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
                logging.info("Creating role for {0}".format(role['group']))
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


class Clusters(ClouderaManagerSetup):


    def init_cluster(self):


        for cluster in config['clusters']:
            try:

                self.cluster[cluster['cluster']] = self.api_resource.get_cluster(cluster['cluster'])
                return self.cluster[cluster['cluster']]

            except ApiException:
                self.cluster[cluster['cluster']] = self.api_resource.create_cluster(cluster['cluster'],
                                                        cluster['version'],
                                                        cluster['fullVersion'])



            cluster_hosts = []
            #
            # Picking up all the nodes from the yaml configuration.
            #
            for host_in_cluster in cluster[cluster['cluster']].list_hosts():
                cluster_hosts.append(host_in_cluster)

            hosts = []

            #
            # Create a host list, make sure we dont have duplicates.
            #
            for host in cluster['hosts']:
                if host not in cluster_hosts:
                    hosts.append(host)

            #
            # Adding all hosts to the cluster.
            #
            cluster[cluster['cluster']].add_hosts(hosts)

        return self.cluster


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

        cloudera_manager_setup = ClouderaManagerSetup(config)
        cloudera_manager_setup.enable_trial_license_for_cm()
        cloudera_manager_setup.host_installation()
        cloudera_manager_setup.deploy_cloudera_management_services()


    except IOError as e:
        logging.error("ERROR {0}. EXIT NOW :( !!!!".format(e))
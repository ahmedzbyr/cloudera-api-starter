
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

if __name__ == '__main__':

    # setting logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    try:
        with open('cloudera_mgmt.yaml', 'r') as cluster_yaml:
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

        # Deploy Management Services
        deploy_management_server(cloudera_manager, config)


    except IOError as e:
        logging.error("ERROR {0}. EXIT NOW :( !!!!".format(e))
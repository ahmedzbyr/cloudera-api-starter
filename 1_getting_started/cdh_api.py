import yaml
import sys
from cm_api.api_client import ApiResource, ApiException



def fail(msg):
    print (msg)
    sys.exit(1)

if __name__ == '__main__':

    # Load the cluster.yaml template and create a Cloudera cluster
    try:
        with open('cloudera.json', 'r') as cluster_yaml:
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
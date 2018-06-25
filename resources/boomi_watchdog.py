#!/usr/bin/python

import socket, subprocess, re, random, sys
from time import sleep
import os.path

# Logging
import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger('boomi-watchdog')
log_file = TimedRotatingFileHandler('/var/log/boomi_watchdog.log', when="D", interval=1, backupCount=30)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
log_file.setFormatter(formatter)
logger.addHandler(log_file)
logger.setLevel(logging.INFO)

# Helper methods
def properties_to_dict(properties_file_path):
    properties_dict = {}
    try:
        for line in open(properties_file_path, 'rb'):
            segments = line.split('=')
            if len(segments) == 2:
                properties_dict[segments[0]] = (segments[1] or "").rstrip()
    except:
        pass
    return properties_dict

def filter_dict(func, d):
    if not isinstance(d, dict):
        return {}
    result_dict = {}
    for k in d.keys():
        if func(k, d[k]):
            result_dict[k] = d[k]
    return result_dict

def no_exception(func, default=False):
    try:
        return func()
    except:
        return default

def check_node(host, port, tries=3):
    logger.info("Start checking connection to host - {host}:{port}".format(host=host, port=port))
    success = False
    for i in xrange(0, tries):
        # Create TCP socket on port 7800
        socket.setdefaulttimeout(5)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Check if socket is active
        result = sock.connect_ex((host, int(port)))
        success = result == 0
        if not success and i < tries-1:
            # Failure
            # Try a node restart and wait a bit
            seconds_to_wait = random.uniform(5, 10) * tries
            logger.warning("Could not establish a TCP connection to {host}:{port}. "\
                           "Wait {seconds} seconds and retry!".format(host=host, port=port,seconds=seconds_to_wait))
            sleep( seconds_to_wait )
        else:
            break

    if success:
        logger.info("Success")
    else:
        logger.error("Fail")
    return success

#CONSTANTS
DEAD_FILE_PATH = "/tmp/DEAD"
LOCAL_IP = subprocess.check_output(["curl", "--silent", "http://169.254.169.254/latest/meta-data/local-ipv4"])
INSTANCE_ID = subprocess.check_output(["curl", "--silent", "http://169.254.169.254/latest/meta-data/instance-id"])
BOOMI_PROPERTIES_FILE_PATH = '/mnt/data/{{BoomiType}}_{{BoomiName}}/conf/container.properties'
BOOMI_VIEWS_FILE_PATH = '/mnt/data/{{BoomiType}}_{{BoomiName}}/bin/views/node.' + LOCAL_IP.replace(".", "_") + '.dat'
BOOMI_INITIAL_HOSTS_PROPERTIES_KEY = 'com.boomi.container.cloudlet.initialHosts'
DEFAULT_JQGROUPS_PORT = 7800

def get_initial_hosts_dict():
    return dict(
        filter(
            lambda element: element is not None,
            map(
                lambda host_port: no_exception(lambda: re.match(r'([^\[]+)\[(.+)\]', host_port).groups(), default=None),
                properties_to_dict(BOOMI_PROPERTIES_FILE_PATH).get(BOOMI_INITIAL_HOSTS_PROPERTIES_KEY, "").split(',')
            )
        )
    )

def get_boomi_view_host_ip_addresses():
    return map(
        lambda host: host.replace('_', '.'),
        filter_dict(
            lambda k, _: re.match(r'view.nodes.[0-9]+', k) is not None,
            properties_to_dict(BOOMI_VIEWS_FILE_PATH) or {}).values()
    )

def restart_boomi():
    logger.info("Restart Boomi service")
    no_exception(lambda: subprocess.check_output(["service", "boomi-atom", "restart"]))

def self_check(tries=3):
    logger.info("Start self check - {host}:{port} - with {num_tries} tries".format(host=LOCAL_IP, port=DEFAULT_JQGROUPS_PORT, num_tries=tries))
    boomi_running = False
    for i in xrange(0, tries):
        boomi_running = no_exception(lambda: "running" in subprocess.check_output(["service", "boomi-atom", "status"]), default=False)
        if boomi_running:
            break
        # Failure
        # Try a node restart and wait a bit
        seconds_to_wait = random.uniform(5, 10) * tries
        logger.warning("Local Boomi service is unhealthy - restart and wait for {seconds}".format(seconds=seconds_to_wait))
        restart_boomi()
        sleep( seconds_to_wait )

    logger.info("SUCCESS" if boomi_running else "FAIL")
    return boomi_running

def update_initial_hosts(new_initial_hosts_dict):
    if not isinstance(new_initial_hosts_dict, dict):
        return
    new_initial_hosts = ",".join(map(
        lambda host_port: "{host}[{port}]".format(host=host_port[0],port=host_port[1]),
        new_initial_hosts_dict.items() or []
    ))
    logger.info("Update initial hosts list. New list = {}".format(new_initial_hosts))
    subprocess.check_output(['sed', '-i', "s/{initialHostsKey}=.*/{initialHostsKey}={initialHosts}/g".format(initialHostsKey=BOOMI_INITIAL_HOSTS_PROPERTIES_KEY, initialHosts=new_initial_hosts), BOOMI_PROPERTIES_FILE_PATH])

def commit_suicide():
    logger.info("Committing suicide!!!")
    # Try graceful shutdown
    no_exception(lambda: subprocess.call(["chkconfig", "boomi-atom", "off"]))
    no_exception(lambda: subprocess.call(["service", "boomi-atom", "stop"]))
    # Tell autoscaling group that the instance is unhealthy
    logger.info("Notify autoscaling group")
    no_exception(lambda: subprocess.check_output(
        ["aws", "autoscaling", "set-instance-health", "--instance-id", INSTANCE_ID, "--health-status", "Unhealthy", "--region", "{{REGION}}"]
    ))
    no_exception(lambda: subprocess.call(["touch", DEAD_FILE_PATH]), default=None)

def is_node_view_consistent_with_initial_hosts(initial_hosts_dict):
    if not isinstance(initial_hosts_dict, dict):
        return False
    return set(initial_hosts_dict.keys()) == set(get_boomi_view_host_ip_addresses())

def is_dead():
    return os.path.exists(DEAD_FILE_PATH)

# MAIN PROGRAM
if __name__ == "__main__":
    if is_dead():
        sys.exit(0)
    healthy = self_check()
    initial_hosts_dict = get_initial_hosts_dict()
    if not healthy:
        logger.error("Boomi service is unrecoverably unhealthy.")
        initial_hosts_dict.pop(LOCAL_IP, None)
        update_initial_hosts(new_initial_hosts_dict=initial_hosts_dict)
        commit_suicide()
    else:
        logger.info("Boomi service is healthy and running.")
        old_initial_hosts_size = len(initial_hosts_dict)
        # Add Local Boomi to initial hosts list
        restart_required = LOCAL_IP not in initial_hosts_dict
        initial_hosts_dict[LOCAL_IP] = DEFAULT_JQGROUPS_PORT

        # Filter unhealthy hosts
        new_initial_hosts_dict = filter_dict(lambda host, port: check_node(host=host, port=port), initial_hosts_dict)
        restart_required = restart_required or len(new_initial_hosts_dict) != old_initial_hosts_size

        # Check if node view is consitent
        restart_required = restart_required or not is_node_view_consistent_with_initial_hosts(initial_hosts_dict=new_initial_hosts_dict)

        # Update inital hosts
        update_initial_hosts(new_initial_hosts_dict=new_initial_hosts_dict)
        if restart_required:
            restart_boomi()



#!/bin/bash

# Install NewRelic Agent
echo "license_key: {{NewrelicLicenceKey}}" | sudo tee -a /etc/newrelic-infra.yml
LOCAL_IP=$(curl --silent http://169.254.169.254/latest/meta-data/local-ipv4) &&\
  echo "display_name: $LOCAL_IP-{{BoomiName}}-{{BoomiType}}-Node" | sudo tee -a /etc/newrelic-infra.yml
curl -o /etc/yum.repos.d/newrelic-infra.repo https://download.newrelic.com/infrastructure_agent/linux/yum/el/6/x86_64/newrelic-infra.repo
yum -q makecache -y --disablerepo='*' --enablerepo='newrelic-infra'
yum install newrelic-infra -y
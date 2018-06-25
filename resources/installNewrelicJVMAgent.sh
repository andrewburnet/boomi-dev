#!/bin/bash

# Install NewRelic Agent
# Download from NewRelic
curl https://download.newrelic.com/newrelic/java-agent/newrelic-agent/current/newrelic-java.zip -o "/usr/local/boomi/newrelic-java.zip"
unzip -o "/usr/local/boomi/newrelic-java.zip" "newrelic/*" -d "/usr/local/boomi/"
# Add license
sed -i 's/license_key:.*/license_key: {{NewrelicLicenceKey}}/g' /usr/local/boomi/newrelic/newrelic.yml
# Configure NewRelic App name
sed -i 's/app_name:.*/app_name: {{APPNAME}}/g' /usr/local/boomi/newrelic/newrelic.yml
# Set log level
sed -i 's/log_level:.*/log_level: finer/g' /usr/local/boomi/newrelic/newrelic.yml
# Add NewRelic Agent to JVM args
! grep -qs "newrelic.jar" /mnt/data/{{BoomiType}}_{{BoomiName}}/bin/atom.vmoptions && echo '-javaagent:/usr/local/boomi/newrelic/newrelic.jar' >> /mnt/data/{{BoomiType}}_{{BoomiName}}/bin/atom.vmoptions || true
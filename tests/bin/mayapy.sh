#!/bin/bash
pythonpath=$PYTHONPATH
projects=$AVALON_PROJECTS
workdir=$AVALON_WORKDIR
/usr/bin/docker exec -e PYTHONPATH=${pythonpath//$HOST_WORKDIR/$DOCKER_WORKDIR} \
					 -e AVALON_PROJECTS=${projects//$HOST_WORKDIR/$DOCKER_WORKDIR} \
					 -e AVALON_PROJECT=$AVALON_PROJECT \
					 -e AVALON_ASSET=$AVALON_ASSET \
					 -e AVALON_SILO=$AVALON_SILO \
					 -e AVALON_TASK=$AVALON_TASK \
					 -e AVALON_APP=$AVALON_APP \
					 -e AVALON_WORKDIR=${workdir//$HOST_WORKDIR/$DOCKER_WORKDIR} \
					 -e AVALON_CONFIG=$AVALON_CONFIG \
					 -e AVALON_LABEL=$AVALON_LABEL \
					 -e AVALON_TIMEOUT=$AVALON_TIMEOUT \
					 -e AVALON_DB=$AVALON_DB \
					 -e AVALON_LOCATION=$AVALON_LOCATION \
					 -e AVALON_CONTAINER_ID=$AVALON_CONTAINER_ID \
					 -e AVALON_DEBUG=$AVALON_DEBUG \
					 maya mayapy $1 "$2"
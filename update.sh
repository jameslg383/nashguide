#!/bin/bash
cd /opt/nashguide
git pull
docker compose up -d --build
echo done

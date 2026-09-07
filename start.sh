#!/bin/bash
cd "/Users/andrejkuvsinov/TG Source Radar"
open -a "Docker" 2>/dev/null
sleep 3
docker compose up --build

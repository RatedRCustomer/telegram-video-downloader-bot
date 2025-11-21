#!/bin/bash
# Bot monitoring script

while true; do
    echo "=== $(date) ==="
    echo "🔍 System Status:"
    
    # Memory usage
    free -h | grep -E "Mem|Swap"
    
    # CPU usage  
    echo "CPU: $(cat /proc/loadavg)"
    
    # Docker containers
    echo "📦 Containers:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
    
    # API health
    echo "🌐 API Health:"
    curl -s http://localhost:8081/health | jq '.system'
    
    # Disk usage
    echo "💾 Downloads:"
    du -sh downloads/
    
    echo "================================"
    sleep 30
done

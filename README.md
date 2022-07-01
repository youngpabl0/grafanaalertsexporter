
# Grafana Alerts Exporter

This script export alerts from Grafana (>8.4) dashboard by url and write them to file (json or yaml)

## Run Locally

Clone the project

```bash
  git clone https://github.com/youngpabl0/grafanaalertsexporter
```

Go to the project directory

```bash
  cd grafanaalertsexporter
```

Install dependencies

```bash
  pip install -r requirements.txt
```

Example run

```bash
  main.py -d https://grafana.site.com/grafana/d/123asd/dashboardName?orgId=1 -a https://grafana.site.com/grafana/api -gt <Bearer grafana token> -m
```

## Run Options 
```-j``` = Run for just get alerts with targets from dashboard

```-m``` = Run for get moira + graphit metrics alerting (alert.yaml)


### F.A.Q
- alerts in yaml are generated for moira with saturations, link section and other specified stuff
- default yaml triggers in lib.defaults.py
- it's open sourced script, u can send PR / commits / fork it, i will appreciate for them
- default yaml alerting are placed in add_def_alerting, u can change it by yourself

have a nice day
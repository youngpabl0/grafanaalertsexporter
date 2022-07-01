import logging
import yaml
import json
from copy import deepcopy
from argparse import ArgumentParser, BooleanOptionalAction
from lib.clients.grafana import GrafanaClient
from lib.defaults import default_alerts_json, default_trigger


class MyDumper(yaml.SafeDumper):
    # HACK: intend
    def increase_indent(self, flow=False, indentless=False):
        return super(MyDumper, self).increase_indent(flow, False)

    # HACK: insert blank lines between top-level objects
    def write_line_break(self, data=None):
        super().write_line_break(data)
        if len(self.indents) == 1:
            super().write_line_break()
        if len(self.indents) == 2:
            super().write_line_break()


def add_trigger(alerts_json, desc, targets, name, expression, ttl, ttl_state,
                dashboard, tags, pending_interval, saturation):
    """add trigger to alerts_json"""
    if saturation:
        trigger = {"name": f"{name}",
                   "desc": f">-\n[action]\n{desc}",
                   "targets": targets,
                   "ttl": ttl,
                   "ttl_state": ttl_state,
                   "expression": expression,
                   "dashboard": dashboard,
                   "pending_interval": pending_interval,
                   "tags": tags,
                   "saturation": saturation
                   }
    else:
        trigger = {"name": f"{name}",
                   "desc": f">-\n[action]\n{desc}",
                   "targets": targets,
                   "ttl": ttl,
                   "ttl_state": ttl_state,
                   "expression": expression,
                   "dashboard": dashboard,
                   "pending_interval": pending_interval,
                   "tags": tags,
                   }
    # fix break lines and type errors
    typing_errors = {"<v": "<", " \n": "\n"}
    for k, v in typing_errors.items():
        trigger['desc'] = trigger['desc'].replace(k, v)
    alerts_json["triggers"].append(trigger)


def add_def_alerting(alerts_json, tags):
    # it's def for me, u can change it for yourself
    """add default level 1 subscription to alert.yaml"""
    alerts_json["alerting"] = [{
        "tags": tags, "contacts": [{"type": "slack", "value": "#spb_monitoring"},
                                   {"type": "jira",
                                    "value": "group_spb_monitoring"}]}]
    return alerts_json["alerting"]


def main():
    test_dashboard = grafana_client.get_dashboard(
        grafana_client.get_dashboard_uid(args['dashboard_link']))
    if test_dashboard.status_code == 200:
        dashboard_info = test_dashboard.json()
        if dashboard_info:
            if dashboard_info['dashboard'].get('id'):
                logger.info('Grafana dashboard ' +
                            dashboard_info['dashboard'].get('title') + ' successfully parsed!')
                if args['json_option']:
                    grafana_data = []
                    for panel in dashboard_info['dashboard'].get("panels"):
                        if grafana_client.get_alert(panel.get('id'), dashboard_info):
                            grafana_data.append(grafana_client.get_alert(
                                panel.get('id'), dashboard_info, unparsed=True))
                    with open(dashboard_info['dashboard'].get('title')+'.json', 'w', encoding='utf-8') as j:
                        j.write(json.dumps(grafana_data,
                                ensure_ascii=False, indent=2))
                elif args['moira_option']:
                    alerts_json = deepcopy(default_alerts_json)
                    for panel in dashboard_info['dashboard'].get("panels"):
                        if grafana_client.get_alert(panel.get('id'), dashboard_info):
                            grafana_data = grafana_client.get_alert(
                                panel.get('id'), dashboard_info)
                            add_trigger(alerts_json=alerts_json,
                                        desc=grafana_data.get(
                                            'desc'),
                                        targets=grafana_data.get('targets'),
                                        name=grafana_data.get("name"),
                                        expression=grafana_data.get(
                                            'expression'),
                                        ttl=grafana_data.get(
                                            'ttl', default_trigger.get('ttl')),
                                        ttl_state=grafana_data.get(
                                            'ttl_state', default_trigger.get('ttl_state')),
                                        dashboard=grafana_data.get(
                                            'dashboard'),
                                        tags=grafana_data.get(
                                            'tags', []) + ["MONAD"],
                                        pending_interval=grafana_data.get(
                                            'pending_interval', default_trigger.get('pending_interval')),
                                        saturation=grafana_data.get('saturation'))
                    add_def_alerting(alerts_json=alerts_json,
                                     tags=grafana_data.get('tags', [])+["MONAD"])
                    with open(dashboard_info['dashboard'].get('title')+'.yaml', 'w', encoding='utf-8') as alerts_yaml:
                        alerts_yaml.write(yaml.dump(alerts_json, default_flow_style=False,
                                                    Dumper=MyDumper, allow_unicode=True, sort_keys=False, width=2000))
                else:
                    logger.info(
                        'You dont select any option, i just parse dashboard, see --help!')
    else:
        logger.warning(
            f"Response from grafana: {test_dashboard.status_code}, check your dashboard link")


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(format="[%(asctime)s][%(levelname)s][%(funcName)s]:%(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    # Configure command line args parsing
    parser = ArgumentParser()
    parser.add_argument("-d", "--dashboard", dest="dashboard_link",
                        help="dashboard link for exporting alerting",
                        metavar="D", required=True)
    parser.add_argument("-a", "--api", dest="api_url",
                        help="example: https://grafana.site.com/grafana/api",
                        metavar="a", required=True)
    parser.add_argument("-gt", "--token", dest="token",
                        help="without token i cant do anything",
                        metavar="gt", required=True)
    parser.add_argument("-j", "--json", dest="json_option", action=BooleanOptionalAction,
                        help="must be True for make json alerting",
                        metavar="J")
    parser.add_argument("-m", "--moira", dest="moira_option", action=BooleanOptionalAction,
                        help="must be True for make moira+graphite alerting",
                        metavar="m")
    args = vars(parser.parse_args())
    # Configure Grafana client
    grafana_client = GrafanaClient(
        api_url=args['api_url'],
        token=args['token'])
    main()

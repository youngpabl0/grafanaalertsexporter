import logging
import re
import urllib.parse
import requests

logger = logging.getLogger()


class GrafanaAlert:
    def __init__(self, panel_data: dict, panel_url: str, panel_tags: list):
        targets = panel_data.get("targets")
        alert = panel_data.get("alert")
        links = panel_data.get("links")
        self.panel_url = panel_url
        self.panel_tags = panel_tags
        if alert and targets:
            self.targets = targets
            self.alert = alert
            self.links = links if links else None
            self.parsed = self.parse_alert()
        else:
            raise ValueError("No alert or trigger information on this panel")

    def get_moira_alert(self) -> dict:
        return self.parsed

    def parse_alert(self) -> dict:
        name = self.alert["name"].replace(' alert', '')
        # Transform targets to dictionary {"refId": target}
        targets = {tgt["refId"]: self.get_target_metric(
            tgt) for tgt in self.targets}
        saturations = []
        used_targets = []
        expression = ''
        for index, condition in enumerate(self.alert["conditions"], start=1):
            evaluator = self.parse_evaluator(condition.get("evaluator"))
            query = self.parse_query(condition.get("query"))
            reducer = self.parse_reducer(condition.get("reducer"))
            operator = self.parse_operator(condition.get("operator"))

            target_key = f"t{index}"
            operator = f" {operator} " if index != 1 else ''
            d = {"target": targets.get(query["target"], "").replace(
                "\"", "'"), "from": query["from"]}
            target = reducer.format_map(d)
            used_targets.append(target)
            expression += f"{operator}{evaluator.format(target=target_key)}"

        expression += " ? ERROR : OK"
        ttl_state, ttl = self.parse_ttl(self.alert)
        if self.links:
            links = self.links
            for link in links:
                one_saturation = {"type": 'take-screenshot',
                                  "parameters": {"url": f"{link.get('url')}", "caption": f"{link.get('title')}"}}
                saturations.append(one_saturation)
            return {"name": name, "desc": self.alert.get("message", "") + self.desc_add(self), "targets": used_targets,
                    "ttl": ttl * 2, "ttl_state": ttl_state, "expression": expression,
                    "pending_interval": ttl, "dashboard": self.panel_url, "tags": self.panel_tags, "saturation": saturations}
        else:
            return {"name": name, "desc": self.alert.get("message", "") + self.desc_add(self), "targets": used_targets,
                    "ttl": ttl * 2, "ttl_state": ttl_state, "expression": expression,
                    "pending_interval": ttl, "dashboard": self.panel_url, "tags": self.panel_tags}

    @staticmethod
    def desc_add(self) -> dict:
        text_to_add = "\n[links]\n"\
            f"• <{self.panel_url}|Grafana>"
        return text_to_add

    @staticmethod
    def parse_ttl(alert: dict):
        states = {
            "alerting": "ERROR",
            "no_data": "NODATA",
            "keep_state": "OK",
            "ok": "OK"
        }
        multiplier = {
            "h": 3600,
            "m": 60,
            "s": 1
        }
        ttl_base = int(''.join(filter(str.isdigit, alert.get("for", "0m"))))
        ttl_multiplier = ''.join(filter(str.isalpha, alert.get("for", "0m")))
        ttl_state = states.get(alert["noDataState"])

        ttl = ttl_base * multiplier.get(ttl_multiplier, 0)
        return ttl_state, ttl

    @staticmethod
    def parse_evaluator(evaluator: dict):
        """Get Moira expression from Grafana conditions. gt > lt <"""
        relation_operators = {"gt": "{{target}} > {}",
                              "lt": "{{target}} < {}",
                              "outside_range": "({{target}} < {} && {{target}} > {})",
                              "within_range": "{} >= {{target}} >= {}",
                              "no_value": None}
        operator = relation_operators.get(evaluator["type"])
        if isinstance(operator, str):
            return operator.format(*sorted(evaluator["params"]))
        else:
            logger.warning(
                f"Unable to parse evaluator: {evaluator}", exc_info=True)
            return None

    @staticmethod
    def parse_query(query: dict):
        try:
            return {"target": query["params"][0], "from": query["params"][1], "to": query["params"][2]}
        except (AttributeError, IndexError) as e:
            logger.exception(e)
            return None

    @staticmethod
    def parse_reducer(reducer: dict):
        agg_functions = {
            "last": "{target}",
            "avg": "movingAverage({target}, '{from}')",
            "min": "movingMin({target}, '{from}')",
            "max": "movingMax({target}, '{from}')",
            "sum": "movingSum({target}, '{from}')",
            "median": "movingMedian({target}, '{from}')",
            "diff": "diffSeries({target}, timeShift({target}, '{from}'))",
            "percent_diff": "asPercent(diffSeries({target}, timeShift({target}, '{from}')), timeShift({target}, '{from}'))",
            "diff_abs": "absolute(diffSeries({target}, timeShift({target}, '{from}')), timeShift({target}, '{from}'))",
            "percent_diff_abs": "asPercent(absolute(diffSeries({target}, timeShift({target}, '{from}')), timeShift({target}, '{from}')))",
        }
        grafana_function = reducer.get('type')
        if grafana_function in agg_functions:
            return agg_functions[grafana_function]
        else:
            logger.warning(f"Unknown agg function: {grafana_function}")
            return "{target}"

    @staticmethod
    def parse_operator(operator: dict):
        logical_operators = {
            "and": "&&",
            "or": "||"
        }
        if "type" in operator:
            return logical_operators.get(operator["type"])
        else:
            logger.warning(f"Logical operator not found: {operator}")
            return None

    @staticmethod
    def get_target_metric(target: dict):
        if isinstance(target, dict):
            if "targetFull" in target:  # and target['refCount'] > 0:
                return target["targetFull"]
            else:
                return target.get("target")
        else:
            return None


class GrafanaClient:
    def __init__(self, api_url, token):
        if not (token and api_url):
            logger.error(
                "Couldn't initialize Grafana client (missing URL or Auth Token)")
        self.api_url = api_url
        self.header = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        }

    def _request(self, path: str):
        try:
            response = requests.get(
                self.api_url + path, headers=self.header, timeout=5)
        except requests.ConnectionError as e:
            logger.error(f"ConnectionError: {e}")
            response = None
        return response

    def get_dashboard_uid(self, dashboard_link: str):
        """Get Grafana dashboard uid by link"""
        parsed = urllib.parse.urlparse(
            dashboard_link)
        match = re.match(
            "^(/\w+)(/\w+)/(?P<uid>\w+)", parsed.path)
        if match:
            dashboard_info_from_path = match.groupdict()
            dashboard_uid = dashboard_info_from_path['uid']
        else:
            dashboard_uid = None
        return dashboard_uid

    def get_dashboard(self, uid: str):
        """Get Grafana dashboard json by uid"""
        return self._request(f"/dashboards/uid/{uid}")

    def get_panel_info(self, dashboard_info, panel_id):
        if dashboard_info:
            # Filter by panelId
            panels = {p["id"]: p for p in dashboard_info["panels"]
                      if p["type"] != "row"}
            panels.update({subpanel["id"]: subpanel for p in dashboard_info["panels"] for subpanel in p.get('panels', [])
                           if p["type"] == "row"})
            panel = panels.get(panel_id)
            if panel and panel.get("targets") and panel.get("alert"):
                if panel.get("links"):
                    return {"targets": panel.get("targets"), "alert": panel.get("alert"), "links": panel.get("links")}
                else:
                    return {"targets": panel.get("targets"), "alert": panel.get("alert")}
        else:
            logger.error("No dashboard_info in get_panel_info")

    def get_alert(self, panel_id, dashboard_info, unparsed=False):
        dashboard = dashboard_info.get('dashboard')
        dashboard_meta = dashboard_info.get('meta')
        logger.debug(
            f"Fetching alert from {dashboard.get('title')} and {panel_id}")
        panel_data = self.get_panel_info(dashboard, panel_id)
        if panel_data and panel_data.get("targets") and panel_data.get("alert"):
            if unparsed:
                just_data = {"targets": panel_data.get("targets"),
                             "alert": panel_data.get("alert")}
                return just_data
            else:
                parsed_url = urllib.parse.urlparse(self.api_url)
                api_url = parsed_url.scheme + '://' + parsed_url.netloc + '/'
                panel_url = api_url + \
                    dashboard_meta.get('url') + \
                    '?viewPanel=' + str(panel_id)
                parsed = GrafanaAlert(panel_data, panel_url,
                                      panel_tags=dashboard['tags']).get_moira_alert()
                return parsed
        else:
            return None


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(format="[%(asctime)s][%(levelname)s][%(funcName)s]:%(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

import re
import yaml

def build_datasource_provisioning(spec: dict) -> str:
    datasources_in = spec.get("datasources", [])
    
    # 1. Перевірка: понад одне default
    default_count = sum(1 for ds in datasources_in if ds.get("default") is True)
    if default_count > 1:
        raise ValueError("Може бути лише одне джерело за замовчуванням")

    seen_names = set()
    seen_uids = set()
    processed_datasources = []

    # Визначення джерела за замовчуванням
    has_explicit_default = default_count == 1

    for idx, ds in enumerate(datasources_in):
        name = ds.get("name")
        ds_type = ds.get("type")
        url = ds.get("url", "")

        # 2. Перевірка типу
        if ds_type not in ("prometheus", "loki"):
            raise ValueError(f"Непідтримуваний тип: {ds_type}")

        # 3. Перевірка URL
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"Некоректна адреса: {url}")

        # Генерація / отримання uid
        raw_uid = ds.get("uid")
        if not raw_uid:
            cleaned = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            uid = cleaned
        else:
            uid = raw_uid

        # 4. Перевірка на дублікати імені або uid
        if name in seen_names or uid in seen_uids:
            raise ValueError(f"Дублікат джерела: {name}")

        seen_names.add(name)
        seen_uids.add(uid)

        # Визначення isDefault
        if has_explicit_default:
            is_default = bool(ds.get("default", False))
        else:
            is_default = (idx == 0)

        entry = {
            "name": name,
            "type": ds_type,
            "uid": uid,
            "access": "proxy",
            "url": url,
            "isDefault": is_default,
            "editable": False,
        }

        # jsonData
        json_data = {}
        if ds_type == "prometheus":
            if "interval" in ds:
                json_data["timeInterval"] = ds["interval"]
        elif ds_type == "loki":
            if "max_lines" in ds:
                json_data["maxLines"] = ds["max_lines"]
            if "derived" in ds:
                derived = ds["derived"]
                json_data["derivedFields"] = [{
                    "name": derived["name"],
                    "matcherRegex": derived["regex"],
                    "url": derived["url"],
                }]
        if json_data:
            entry["jsonData"] = json_data

        # basicAuth & secureJsonData
        if "basic_auth_user" in ds:
            entry["basicAuth"] = True
            entry["basicAuthUser"] = ds["basic_auth_user"]
            pwd_env = ds.get("password_env", "")
            entry["secureJsonData"] = {
                "basicAuthPassword": f"${{{pwd_env}}}"
            }

        processed_datasources.append(entry)

    result_dict = {
        "apiVersion": 1,
        "datasources": processed_datasources,
    }

    return yaml.safe_dump(result_dict, allow_unicode=True, sort_keys=False)
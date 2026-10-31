import yaml


def load_config(text):
    # VULN: unsafe deserialization (yaml.Loader can build arbitrary objects)
    return yaml.load(text, Loader=yaml.Loader)

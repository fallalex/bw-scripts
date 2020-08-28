import json
import sys
import pickle
import pyotp
import os
from .denConf import denConf
from .bwSession import bwSession

def _finditem(obj, key):
    if key in obj: return (True, obj[key])
    for k, v in obj.items():
        if isinstance(v, dict):
            exists, value = _finditem(v, key)
            if exists: return (exists, value)
    return (False, None)

class bwHelper:
    def __init__(self):
        self.config = denConf()
        self.bwsess = bwSession(self.config)
        self.gpg = self.bwsess.gpg
        self.bwcli = self.bwsess.bwcli
        self.cache_dict = {}
        for obj_type in self.config.cache_obj_types:
            self.cache_dict[obj_type] = {}

    def refresh(self):
        if self.config.pickle and self.config.pickle_path.is_file():
            self.bwsess.decrypt_session()
            with open(self.config.pickle_path, 'rb') as f:
                self.cache_dict = pickle.load(f)
        else:
            self.bwsess.new_session()
            out = self.bwcli.sync()
            for obj in list(self.cache_dict.keys()):
                out = self.bwcli.list(obj)
                try: self.cache_dict[obj] = json.loads(out)
                except: sys.exit("Failed to parse json from '{}'.".format(obj))
            if self.config.pickle:
                with open(self.config.pickle_path, 'wb') as f:
                    pickle.dump(self.cache_dict, f)
            else:
                if self.config.pickle_path.is_file():
                    self.config.pickle_path.unlink()
        self.cache_redact()
        if self.config.pickle:
            with open(self.config.redacted_pickle_path, 'wb') as f:
                pickle.dump(self.cache_dict, f)
        else:
            if self.config.redacted_pickle_path.is_file():
                self.config.redacted_pickle_path.unlink()
        self.gpg.encrypt_to_file(json.dumps(self.cache_dict), self.config.cache_path)

    #TODO: hmm this does not seem ideal...
    def cache_redact(self):
        for obj_type in list(self.cache_dict.keys()):
            for obj_idx in range(len(self.cache_dict[obj_type])):
                for k in list(self.cache_dict[obj_type][obj_idx].keys()):
                    if k not in self.config.cache_obj_fields:
                        del self.cache_dict[obj_type][obj_idx][k]
                        continue
                    # redact creds to bool
                    if k in self.config.cache_obj_fields_redact:
                        if k == 'login':
                            self.cache_dict[obj_type][obj_idx]['password'] = bool(self.cache_dict[obj_type][obj_idx][k]['password'])
                            self.cache_dict[obj_type][obj_idx]['totp'] = bool(self.cache_dict[obj_type][obj_idx][k]['totp'])
                            del self.cache_dict[obj_type][obj_idx][k]
                        else:
                            self.cache_dict[obj_type][obj_idx][k] = bool(self.cache_dict[obj_type][obj_idx][k])

    def decrypt_cache(self):
        self.cache_dict = self.gpg.decrypt_file(self.config.cache_path)
        if not self.cache_dict:
            sys.exit("Failed to decrypt cache or empty file. Try this command\n  gpg --decrypt '{}'".format(self.config.cache_path))
        try: self.cache_dict = json.loads(self.cache_dict)
        except: sys.exit("Failed to parse json from '{}'.".format(self.config.cache_path))
        assert(self.config.cache_obj_types == set(self.cache_dict.keys()))

    def completion(self, obj_type):
        assert(obj_type in self.config.cache_obj_types | {'all'})
        if obj_type == 'all':
            return json.dumps(self.cache_dict)
        names = set()
        for obj in self.cache_dict[obj_type]:
            assert('name' in obj)
            names.add(obj['name'])
        return '\n'.join(sorted(names))

    def get_pass(self, id):
        return self.get_item(id, 'password')

    def get_totp(self, id):
        token = self.get_item(id, 'totp')
        if token:
            return pyotp.TOTP(token).now()
        print("No TOTP")
        os._exit(1)

    def get_item(self, id, field=None):
        item = self.bwcli.get(id)
        if field:
            exists, value = _finditem(item, field)
            if not exists:
                print("The field '{}' is not in id '{}'.".format(field, id))
                os._exit(1)
            return value
        return item

    def item_id(self, name):
        for i in self.cache_dict['items']:
            # This only finds the first match ignores any others
            if name == i['name']:
                return i['id']


from collections import defaultdict, namedtuple

import okta.models
from okta.errors.okta_api_error import OktaAPIError


class ResponseDetails:
    def __init__(self, status=None, headers=None):
        self.status = status
        self.headers = headers

    def has_next(self):
        return False


class FakeOktaClient:
    def __init__(self):
        # state management
        self.user_auto_increment_id = 0
        self.username_to_user = {}
        # user_id is a string
        self.user_id_to_user = {}

        self.group_auto_increment_id = 0
        self.groupname_to_group = {}
        # group_id is a string
        self.group_id_to_group = {}
        self.group_id_to_user_ids = defaultdict(set)

    async def get_user(self, *args, **kwargs):
        login = args[0]
        if login in self.username_to_user:
            user = self.username_to_user[login]
            return (user, ResponseDetails(status=200, headers={}), defaultdict(list))
        elif login in self.user_id_to_user:
            user = self.user_id_to_user[login]
            return (user, ResponseDetails(status=200, headers={}), defaultdict(list))
        else:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )

    async def list_users(self, *args, **kwargs):
        return (
            self.username_to_user.values(),
            ResponseDetails(status=200, headers={}),
            defaultdict(list),
        )

    async def create_user(self, config: dict):
        login = config["profile"]["login"]

        if login in self.username_to_user:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )
        else:
            user = okta.models.User(config)
            user.profile = okta.models.user_profile.UserProfile(config["profile"])
            user.login = config["profile"]["login"]
            user.id = self.user_auto_increment_id
            user.status = okta.models.UserStatus.ACTIVE
            self.user_auto_increment_id += 1
            self.username_to_user[user.login] = user
            self.user_id_to_user[f"{user.id}"] = user
            return (user, ResponseDetails(status=200, headers={}), defaultdict(list))

    async def update_user(self, user_id, properties: dict):
        login = user_id
        if login in self.user_id_to_user:
            user = okta.models.User()
            if isinstance(properties, okta.models.User):
                input_user: okta.models.User = properties
                user.profile = input_user.profile
            else:
                if "status" in properties:
                    user.status = properties["status"]
                user.profile = okta.models.user_profile.UserProfile(properties)
                user.profile.login = login
                user.id = user_id
            return (user, ResponseDetails(status=200, headers={}), defaultdict(list))
        else:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )

    async def deactivate_or_delete_user(self, user_id):
        user = self.user_id_to_user[user_id]
        del self.username_to_user[user.profile.login]
        del self.user_id_to_user[f"{user.id}"]
        return (ResponseDetails(status=200, headers={}), defaultdict(list))

    async def create_group(self, group_model: okta.models.Group):
        groupname = group_model.profile.name

        if groupname in self.groupname_to_group:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )
        else:
            group = okta.models.Group(group_model.as_dict())
            group.id = self.group_auto_increment_id
            self.group_auto_increment_id += 1
            self.groupname_to_group[group.profile.name] = group
            self.group_id_to_group[f"{group.id}"] = group
            return (group, ResponseDetails(status=200, headers={}), defaultdict(list))

    async def delete_group(self, group_id: str):

        if group_id not in self.group_id_to_group:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )
        else:
            group = self.group_id_to_group[group_id]
            del self.groupname_to_group[group.profile.name]
            del self.group_id_to_group[group_id]
            return (ResponseDetails(status=200, headers={}), defaultdict(list))

    async def update_group(self, group_id, group_model: okta.models.Group):
        groupname = group_model.profile.name

        if group_id not in self.group_id_to_group:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )
        else:
            group = self.group_id_to_group[group_id]
            group.id = self.group_auto_increment_id
            old_group_name = group.profile.name
            group.profile = group_model.profile
            new_group_name = group.profile.name
            self.groupname_to_group[new_group_name] = group
            return (group, ResponseDetails(status=200, headers={}), defaultdict(list))

    async def get_group(self, group_id):
        if group_id in self.group_id_to_group:
            group = self.group_id_to_group[group_id]
            return (group, ResponseDetails(status=200, headers={}), defaultdict(list))
        else:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )

    async def list_groups(self, *args, **kwargs):
        query_params = kwargs.get("query_params")
        if query_params:
            group_name = query_params["q"]
            group = self.groupname_to_group.get(group_name)
            return (
                [group] if group else [],
                ResponseDetails(status=200, headers={}),
                defaultdict(list),
            )
        else:
            return (
                self.groupname_to_group.values(),
                ResponseDetails(status=200, headers={}),
                defaultdict(list),
            )

    async def add_user_to_group(self, group_id, user_id: list[int]):
        self.group_id_to_user_ids[group_id].add(f"{user_id}")
        return ResponseDetails(status=200, headers={}), defaultdict(list)

    async def remove_user_from_group(self, group_id, user_id: int):
        self.group_id_to_user_ids[group_id].remove(f"{user_id}")
        return ResponseDetails(status=200, headers={}), defaultdict(list)

    async def list_group_users(self, group_id):
        user_ids = self.group_id_to_user_ids[group_id]
        users = [self.user_id_to_user[user_id] for user_id in user_ids]
        return (users, ResponseDetails(status=200, headers={}), defaultdict(list))

"""Offline permission boundary, replacement transaction, and input validation tests."""
import importlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for key in list(os.environ):
    if key.startswith(("DB_", "PG", "AWS_")):
        os.environ.pop(key, None)
os.environ["AWS_PROFILE"] = os.environ["AWS_DEFAULT_PROFILE"] = "imhealth-dev"
def forbidden(*args, **kwargs):
    raise AssertionError("External calls forbidden")
pg=types.ModuleType("psycopg2"); pg.connect=forbidden; pg.Error=Exception
extra=types.ModuleType("psycopg2.extras"); extra.RealDictCursor=object
sys.modules["psycopg2"]=pg;sys.modules["psycopg2.extras"]=extra
aws=types.ModuleType("boto3");aws.client=aws.resource=aws.Session=forbidden;sys.modules["boto3"]=aws
from utils import admin_permissions as auth
from generic_dals.permissions_dal import PermissionsDAL
handler=importlib.import_module("services.admin_permissions.admin_permissions")

def event():
    return {"path":"/role-permissions", "httpMethod":"GET", "requestContext":{"authorizer":{"claims":{"sub":"subject", "email":"ADMIN@EXAMPLE.EDU", "email_verified":"true", "custom:is_student":"false"}}}}

class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.dal=Mock();self.dal.identity.return_value={"role_id":1,"role_name":"guidance_counselor"}
        self.dal.permissions.return_value={"students":["read"]}
        patcher=patch.object(auth,"PermissionsDAL",return_value=self.dal);patcher.start();self.addCleanup(patcher.stop)
    def test_read_allowed_upload_and_insert_denied(self):
        self.assertIsNone(auth.require_permission(event(),None,"students","read"))
        for action in ("insert","update","upload","download"):
            self.assertEqual(auth.require_permission(event(),None,"students",action)["statusCode"],403)
    def test_missing_verified_identity_fails_before_dal(self):
        e=event();e["requestContext"]["authorizer"]["claims"].pop("email_verified")
        self.assertEqual(auth.require_permission(e,None,"students","read")["statusCode"],401)
        self.dal.identity.assert_not_called()
    def test_claim_without_database_admin_is_denied(self):
        self.dal.identity.return_value=None
        self.assertEqual(auth.require_permission(event(),None,"students","read")["statusCode"],403)
    def test_non_super_admin_cannot_manage_even_with_forged_grants(self):
        self.dal.permissions.return_value={"permissions":["read","update"]}
        self.assertEqual(auth.require_permission(event(),None,"permissions","read")["statusCode"],403)

class ReplacementTests(unittest.TestCase):
    def setUp(self):
        self.dal=PermissionsDAL.__new__(PermissionsDAL);self.dal.db=Mock()
        self.dal._fetch_one=Mock(return_value={"id":1,"role_name":"guidance_counselor"})
        self.dal.matrix=Mock(return_value={"modules":[{"id":1,"module_key":"students"},{"id":2,"module_key":"permissions"}],"permission_types":[{"id":1}]})
    def test_replacement_is_locked_and_committed_once(self):
        self.dal.replace(1,[(1,1)])
        self.assertIn("FOR UPDATE", self.dal._fetch_one.call_args.args[0])
        self.assertEqual(self.dal.db.execute_modification.call_count,2)
        self.dal.db.conn.commit.assert_called_once()
    def test_invalid_or_manager_grant_does_not_delete(self):
        for grants in ([(9,1)],[(1,9)],[(2,1)]):
            with self.assertRaises(ValueError):self.dal.replace(1,grants)
        self.dal.db.execute_modification.assert_not_called()
    def test_write_failure_rolls_back(self):
        self.dal.db.execute_modification.side_effect=RuntimeError("failure")
        with self.assertRaises(RuntimeError):self.dal.replace(1,[(1,1)])
        self.dal.db.conn.rollback.assert_called_once();self.dal.db.conn.commit.assert_not_called()
    def test_super_admin_is_immutable(self):
        self.dal._fetch_one.return_value={"id":3,"role_name":"su_admin"}
        with self.assertRaises(ValueError):self.dal.replace(3,[])
        self.dal.db.execute_modification.assert_not_called()

class HandlerTests(unittest.TestCase):
    def test_boolean_grant_identifier_is_rejected(self):
        e=event();e.update(httpMethod="PUT",pathParameters={"role_id":"1"},body=json.dumps({"grants":[{"module_id":True,"permission_type_id":1}]}))
        conn=Mock();dal=Mock()
        with patch.object(handler,"get_db_connection",return_value=conn),patch.object(handler,"PermissionsDAL",return_value=dal),patch.object(handler,"admin_identity",return_value=({"role_id":3,"role_name":"su_admin"},None)),patch.object(handler,"require_permission",return_value=None):
            self.assertEqual(handler.handler(e,None)["statusCode"],400)
        dal.replace.assert_not_called();conn.close.assert_called_once()
if __name__=="__main__":unittest.main()

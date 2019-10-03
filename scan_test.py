# -*- coding: utf-8 -*-
# Upside Travel, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import unittest

import boto3
import botocore.session
from botocore.stub import Stubber

from common import AV_SCAN_START_METADATA
from common import AV_TIMESTAMP_METADATA
from common import get_timestamp
from scan import delete_s3_object
from scan import event_object
from scan import get_local_path
from scan import sns_start_scan
from scan import verify_s3_object_version


class TestScan(unittest.TestCase):
    def setUp(self):
        self.s3_bucket_name = "test_bucket"
        self.s3 = boto3.resource("s3")

        self.s3_client = botocore.session.get_session().create_client("s3")
        self.sns_client = botocore.session.get_session().create_client(
            "sns", region_name="us-west-2"
        )

    def test_sns_event_object(self):
        key_name = "key"
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": self.s3_bucket_name},
                        "object": {"key": key_name},
                    }
                }
            ]
        }
        sns_event = {"Records": [{"Sns": {"Message": json.dumps(event)}}]}
        s3_obj = event_object(sns_event, event_source="sns")
        expected_s3_object = self.s3.Object(self.s3_bucket_name, key_name)
        self.assertEquals(s3_obj, expected_s3_object)

    def test_s3_event_object(self):
        key_name = "key"
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": self.s3_bucket_name},
                        "object": {"key": key_name},
                    }
                }
            ]
        }
        s3_obj = event_object(event)
        expected_s3_object = self.s3.Object(self.s3_bucket_name, key_name)
        self.assertEquals(s3_obj, expected_s3_object)

    def test_s3_event_object_missing_bucket(self):
        key_name = "key"
        event = {"Records": [{"s3": {"object": {"key": key_name}}}]}
        with self.assertRaises(Exception) as cm:
            event_object(event)
        self.assertEquals(cm.exception.message, "No bucket found in event!")

    def test_s3_event_object_missing_key(self):
        event = {"Records": [{"s3": {"bucket": {"name": self.s3_bucket_name}}}]}
        with self.assertRaises(Exception) as cm:
            event_object(event)
        self.assertEquals(cm.exception.message, "No key found in event!")

    def test_s3_event_object_bucket_key_missing(self):
        event = {"Records": [{"s3": {"bucket": {}, "object": {}}}]}
        with self.assertRaises(Exception) as cm:
            event_object(event)
        self.assertEquals(
            cm.exception.message,
            "Unable to retrieve object from event.\n{}".format(event),
        )

    def test_s3_event_object_no_records(self):
        event = {"Records": []}
        with self.assertRaises(Exception) as cm:
            event_object(event)
        self.assertEquals(cm.exception.message, "No records found in event!")

    def test_verify_s3_object_version(self):
        key_name = "key"
        s3_obj = self.s3.Object(self.s3_bucket_name, key_name)

        # Set up responses
        get_bucket_versioning_response = {"Status": "Enabled"}
        get_bucket_versioning_expected_params = {"Bucket": self.s3_bucket_name}
        self.stubber_resource = Stubber(self.s3.meta.client)
        self.stubber_resource.add_response(
            "get_bucket_versioning",
            get_bucket_versioning_response,
            get_bucket_versioning_expected_params,
        )
        list_object_versions_response = {
            "Versions": [
                {
                    "ETag": "string",
                    "Size": 123,
                    "StorageClass": "STANDARD",
                    "Key": "string",
                    "VersionId": "string",
                    "IsLatest": True,
                    "LastModified": datetime.datetime(2015, 1, 1),
                    "Owner": {"DisplayName": "string", "ID": "string"},
                }
            ]
        }
        list_object_versions_expected_params = {
            "Bucket": self.s3_bucket_name,
            "Prefix": key_name,
        }
        self.stubber_resource.add_response(
            "list_object_versions",
            list_object_versions_response,
            list_object_versions_expected_params,
        )
        try:
            with self.stubber_resource:
                verify_s3_object_version(self.s3, s3_obj)
        except Exception as e:
            self.fail("verify_s3_object_version() raised Exception unexpectedly!")
            raise e

    def test_verify_s3_object_versioning_not_enabled(self):
        key_name = "key"
        s3_obj = self.s3.Object(self.s3_bucket_name, key_name)

        # Set up responses
        get_bucket_versioning_response = {"Status": "Disabled"}
        get_bucket_versioning_expected_params = {"Bucket": self.s3_bucket_name}
        self.stubber_resource = Stubber(self.s3.meta.client)
        self.stubber_resource.add_response(
            "get_bucket_versioning",
            get_bucket_versioning_response,
            get_bucket_versioning_expected_params,
        )
        with self.assertRaises(Exception) as cm:
            with self.stubber_resource:
                verify_s3_object_version(self.s3, s3_obj)
        self.assertEquals(
            cm.exception.message,
            "Object versioning is not enabled in bucket {}".format(self.s3_bucket_name),
        )

    def test_verify_s3_object_version_multiple_versions(self):
        key_name = "key"
        s3_obj = self.s3.Object(self.s3_bucket_name, key_name)

        # Set up responses
        get_bucket_versioning_response = {"Status": "Enabled"}
        get_bucket_versioning_expected_params = {"Bucket": self.s3_bucket_name}
        self.stubber_resource = Stubber(self.s3.meta.client)
        self.stubber_resource.add_response(
            "get_bucket_versioning",
            get_bucket_versioning_response,
            get_bucket_versioning_expected_params,
        )
        list_object_versions_response = {
            "Versions": [
                {
                    "ETag": "string",
                    "Size": 123,
                    "StorageClass": "STANDARD",
                    "Key": "string",
                    "VersionId": "string",
                    "IsLatest": True,
                    "LastModified": datetime.datetime(2015, 1, 1),
                    "Owner": {"DisplayName": "string", "ID": "string"},
                },
                {
                    "ETag": "string",
                    "Size": 123,
                    "StorageClass": "STANDARD",
                    "Key": "string",
                    "VersionId": "string",
                    "IsLatest": True,
                    "LastModified": datetime.datetime(2015, 1, 1),
                    "Owner": {"DisplayName": "string", "ID": "string"},
                },
            ]
        }
        list_object_versions_expected_params = {
            "Bucket": self.s3_bucket_name,
            "Prefix": key_name,
        }
        self.stubber_resource.add_response(
            "list_object_versions",
            list_object_versions_response,
            list_object_versions_expected_params,
        )
        with self.assertRaises(Exception) as cm:
            with self.stubber_resource:
                verify_s3_object_version(self.s3, s3_obj)
        self.assertEquals(
            cm.exception.message,
            "Detected multiple object versions in {}.{}, aborting processing".format(
                self.s3_bucket_name, key_name
            ),
        )

    def test_sns_start_scan(self):
        self.stubber = Stubber(self.sns_client)
        self.stubber_resource = Stubber(self.s3.meta.client)

        sns_arn = "some_arn"
        key_name = "key"
        version_id = "version-id"
        timestamp = get_timestamp()
        message = {
            "bucket": self.s3_bucket_name,
            "key": key_name,
            "version": version_id,
            AV_SCAN_START_METADATA: True,
            AV_TIMESTAMP_METADATA: timestamp,
        }
        publish_response = {"MessageId": "message_id"}
        publish_expected_params = {
            "TargetArn": sns_arn,
            "Message": json.dumps({"default": json.dumps(message)}),
            "MessageStructure": "json",
        }
        self.stubber.add_response("publish", publish_response, publish_expected_params)

        head_object_response = {"VersionId": version_id}
        head_object_expected_params = {"Bucket": self.s3_bucket_name, "Key": key_name}
        self.stubber_resource.add_response(
            "head_object", head_object_response, head_object_expected_params
        )
        with self.stubber, self.stubber_resource:
            s3_obj = self.s3.Object(self.s3_bucket_name, key_name)
            sns_start_scan(self.sns_client, s3_obj, sns_arn, timestamp)

    def test_get_local_path(self):
        key_name = "key"
        local_prefix = "/tmp"

        s3_obj = self.s3.Object(self.s3_bucket_name, key_name)
        file_path = get_local_path(s3_obj, local_prefix)
        expected_file_path = "/tmp/test_bucket/key"
        self.assertEquals(file_path, expected_file_path)

    def test_set_av_metadata(self):
        pass

    def test_set_av_tags(self):
        pass

    def test_sns_scan_results(self):
        pass

    def test_delete_s3_object(self):
        key_name = "key"
        stubber = Stubber(self.s3.meta.client)
        delete_object_response = {}
        delete_object_expected_params = {"Bucket": self.s3_bucket_name, "Key": key_name}
        stubber.add_response(
            "delete_object", delete_object_response, delete_object_expected_params
        )

        with stubber:
            s3_obj = self.s3.Object(self.s3_bucket_name, key_name)
            delete_s3_object(s3_obj)

    def test_delete_s3_object_exception(self):
        key_name = "key"
        stubber = Stubber(self.s3.meta.client)

        with self.assertRaises(Exception) as cm:
            with stubber:
                s3_obj = self.s3.Object(self.s3_bucket_name, key_name)
                delete_s3_object(s3_obj)
        self.assertEquals(
            cm.exception.message,
            "Failed to delete infected file: {}.{}".format(
                self.s3_bucket_name, key_name
            ),
        )

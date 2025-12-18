# import boto3
# import json
#
#
# # EC2
# def get_vpcs_list(region, session):
#
#     ec2_client = session.client("ec2")
#     try:
#         response = ec2_client.describe_vpcs()
#         vpcs = [
#             {"VpcId": vpc["VpcId"], "Name": vpc["Tags"][0]["Value"], "Region": region}
#             for vpc in response.get("Vpcs", [])
#         ]
#         return vpcs
#     except Exception as e:
#         print(f"Error fetching VPCs: {str(e)}")
#         return []
#
#
# def get_vpc_subnets(vpc_id, region, session):
#
#     ec2_client = session.client("ec2")
#     response = ec2_client.describe_subnets(
#         Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
#     )
#
#     return [
#         {
#             "SubnetId": subnet["SubnetId"],
#             "Name": subnet["Tags"][0]["Value"],
#             "AvailabilityZone": subnet["AvailabilityZone"],
#             "AvailableIpAddressCount": subnet["AvailableIpAddressCount"],
#         }
#         for subnet in response.get("Subnets", [])
#         if subnet["MapPublicIpOnLaunch"] == False
#     ]
#
#
# def get_vpc_security_groups(vpc_id, region, session):
#
#     ec2_client = session.client("ec2")
#     response = ec2_client.describe_security_groups(
#         Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
#     )
#
#     return [
#         {"GroupId": security_group["GroupId"], "Name": security_group["GroupName"]}
#         for security_group in response.get("SecurityGroups", [])
#     ]
#


import boto3
from botocore.exceptions import ClientError

# ----------------------------
# Client Factory (CORE)
# ----------------------------

def get_aws_client(session, service, region):
    """
    Centralized AWS client factory.
    Enforces region safety.
    """
    if not region:
        raise ValueError("Region must be provided to create AWS client")

    return session.client(service, region_name=region)


# ----------------------------
# Helpers
# ----------------------------

def get_name_from_tags(tags):
    for tag in tags or []:
        if tag.get("Key") == "Name":
            return tag.get("Value")
    return "N/A"


# ----------------------------
# EC2 / VPC FUNCTIONS
# ----------------------------

def get_vpcs_list(region, session):
    ec2 = get_aws_client(session, "ec2", region)

    vpcs = []
    paginator = ec2.get_paginator("describe_vpcs")

    for page in paginator.paginate():
        for vpc in page.get("Vpcs", []):
            vpcs.append({
                "VpcId": vpc["VpcId"],
                "Name": get_name_from_tags(vpc.get("Tags")),
                "Region": region
            })

    return vpcs


def get_vpc_subnets(vpc_id, region, session, private_only=True):
    ec2 = get_aws_client(session, "ec2", region)

    subnets = []
    paginator = ec2.get_paginator("describe_subnets")

    for page in paginator.paginate(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    ):
        for subnet in page.get("Subnets", []):
            if private_only and subnet.get("MapPublicIpOnLaunch", False):
                continue

            subnets.append({
                "SubnetId": subnet["SubnetId"],
                "Name": get_name_from_tags(subnet.get("Tags")),
                "AvailabilityZone": subnet["AvailabilityZone"],
                "AvailableIpAddressCount": subnet["AvailableIpAddressCount"],
            })

    return subnets


def get_vpc_security_groups(vpc_id, region, session):
    ec2 = get_aws_client(session, "ec2", region)

    sgs = []
    paginator = ec2.get_paginator("describe_security_groups")

    for page in paginator.paginate(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    ):
        for sg in page.get("SecurityGroups", []):
            sgs.append({
                "GroupId": sg["GroupId"],
                "Name": sg["GroupName"]
            })

    return sgs


# ----------------------------
# SECURITY GROUP (LAMBDA)
# ----------------------------

def get_or_create_sg(session, region, vpc_id, lambda_name):
    ec2 = get_aws_client(session, "ec2", region)
    sg_name = f"{lambda_name}-sg"

    response = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [sg_name]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )

    if response["SecurityGroups"]:
        return response["SecurityGroups"][0]["GroupId"]

    sg = ec2.create_security_group(
        GroupName=sg_name,
        Description=f"SG for {lambda_name}",
        VpcId=vpc_id,
    )

    return sg["GroupId"]

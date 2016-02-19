'''
The MIT License (MIT)
Copyright (c) 2016 Ian B. Willoughby

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

'''

import boto3
import time
from functools import wraps


def cached_property(fn):
    """
    A decorator that returns a property.

    The method decorated will only be called the
    first time the property is computed.
    """
    @property
    @wraps(fn)
    def _fn(self):
        key = "_memo_%s" % fn.__name__
        if not hasattr(self, key):
            setattr(self, key, fn(self))
        return getattr(self, key)
    return _fn


class NoVpcsException(Exception):
    pass


class VpcHasNatGatewayException(Exception):
    pass


class NatConverter(object):

    def __init__(self):
        self.vpc_id = None
        self.target_subnet = None
        self.eip_allocation_id = None
        self.nat_gateway_id = None

    @cached_property
    def client(self):
        return boto3.client('ec2')

    @cached_property
    def vpcs(self):
        _vpcs = self.client.describe_vpcs()['Vpcs']
        if not _vpcs:
            raise NoVpcsException("No VPCs exist on your account")
        return _vpcs

    def display_vpcs(self):
        index = 1
        for v in self.vpcs:
            name = v['VpcId'] + ' - ' + v['CidrBlock']
            if v['IsDefault']:
                name = name + ' (Default VPC)'
            for t in v.get('Tags', []):
                if t['Key'] == 'Name':
                    if len(t['Value']) > 0:
                        name = name + ' - ' + t['Value']
                    break
            print ('[{}] ' + name).format(index)
            index += 1

    def verify_vpc_is_natless(self, vpc_id=None):
        f = [
            {'Name': 'vpc-id', 'Values': [vpc_id or self.vpc_id]},
            {'Name': 'state', 'Values': ['available']},
        ]
        response = self.client.describe_nat_gateways(Filter=f)
        if len(response['NatGateways']) > 0:
            raise VpcHasNatGatewayException('NAT Gateway already exists for VPC {}!'.format(vpc_id))
        return True

    def select_vpc(self):
        self.display_vpcs()
        input_vpc = raw_input('Select the VPC to analyze: ')
        try:
            input_vpc = int(input_vpc)
        except ValueError:
            print("That's not a valid selection!")
            self.select_vpc()
        if input_vpc < 1 or input_vpc > len(self.vpcs):
            print("That's not a valid selection!")
            self.select_vpc()
        self.vpc_id = self.vpcs[input_vpc - 1]['VpcId']
        self.verify_vpc_is_natless(self.vpc_id)
        print("Selected VPC: {}".format(self.vpc_id))
        return self.vpc_id

    @cached_property
    def route_tables(self):
        f = [
            {'Name': 'vpc-id', 'Values': [self.vpc_id]},
        ]
        return self.client.describe_route_tables(Filters=f)['RouteTables']

    def public_subnets(self):
        for route_table in self.route_tables:
            is_public = False
            for route in route_table['Routes']:
                if 'GatewayId' in route and route['DestinationCidrBlock'] == '0.0.0.0/0':
                    is_public = True
            for assoc in route_table['Associations']:
                if 'SubnetId' in assoc and is_public:
                    yield assoc

    def private_subnets(self):
        for route_table in self.route_tables:
            is_public = False
            for route in route_table['Routes']:
                if 'GatewayId' in route and route['DestinationCidrBlock'] == '0.0.0.0/0':
                    is_public = True
            for assoc in route_table['Associations']:
                if 'SubnetId' in assoc and (not is_public):
                    yield assoc['SubnetId']

    def nat_instances(self):
        """
        All legacy NAT instances on the selected VPC
        """
        for route_table in self.route_tables:
            for route in route_table['Routes']:
                if 'InstanceId' in route:
                    yield {
                        'RouteTableId': route_table,
                        'InstanceId': route['InstanceId'],
                        'DestinationCidrBlock': route['DestinationCidrBlock'],
                    }

    def can_nat_be_converted(self, nat_instance):
        """
        Apparently NAT instances with src/dest check enabled can't be converted
        """
        response = self.client.describe_instance_attribute(InstanceId=nat_instance['InstanceId'], Attribute='sourceDestCheck')
        return response['SourceDestCheck']['Value'] == False

    def convertable_nat_instances(self):
        """
        Only the legacy NAT instances on this VPC that can be replaced with new NAT Gateway instances
        """
        return filter(self.can_nat_be_converted, self.nat_instances())

    def allocate_elastic_ip(self):
        self.eip_allocation_id = self.client.allocate_address(Domain='vpc')['AllocationId']

    def select_target_subnet(self):
        for sub in self.public_subnets():
            print sub
        self.target_subnet = raw_input('Type the ID of the target subnet for the new NAT Gateway: ')
        return self.target_subnet

    def create_nat_gateway(self):
        kwargs = {'SubnetId': self.target_subnet}
        if self.eip_allocation_id:
            kwargs.update({'AllocationId': self.eip_allocation_id})
        response = self.client.create_nat_gateway(**kwargs)
        self.nat_gateway_id = response['NatGateway']['NatGatewayId']
        return self.nat_gateway_id

    def get_nat_gateway_details(self, nat_gateway_id=None):
        nat_gateway_id = nat_gateway_id or self.nat_gateway_id
        f = [
            {'Name': 'vpc-id', 'Values': [self.vpc_id]},
        ]
        return self.client.describe_nat_gateways(
            NatGatewayIds=[nat_gateway_id],
            Filter=f,
        )

    def wait_on_nat_gateways_ready(self, nat_gateway_id):
        """
        Wait on all the NAT Gateway service instances on our selected VPC to be ready
        """
        print 'Waiting on all NAT Gateway instances to become available',
        all_gateways_ready = False
        while not all_gateways_ready:
            response = self.get_nat_gateway_details(nat_gateway_id=nat_gateway_id)
            # if *any* instances exist, optimistically assume that we're ready
            all_gateways_ready = len(response['NatGateways']) > 0
            for g in response['NatGateways']:
                # ...but check each instance and make sure
                if g['State'].lower() != 'available':
                    all_gateways_ready = False
            print '.',
            time.sleep(5)
        print " all ready!"

    def update_routing(self):
        print 'Removing route table entries for old NAT instance(s)... ',
        for instance in self.convertable_nat_instances():
            response = self.client.delete_route(
                RouteTableId=instance['RouteTableId'],
                DestinationCidrBlock=instance['DestinationCidrBlock']
            )
        print 'done. (response={})'.format(response)
        instance = self.get_nat_gateway_details(self.nat_gateway_id)
        print 'Adding route table entry for new NAT instance... ',
        response = self.client.create_route(
            RouteTableId=instance['RouteTableId'],
            DestinationCidrBlock=instance['DestinationCidrBlock'],
            NatGatewayId=self.nat_gateway_id,
        )
        print 'done. (response={})'.format(response)

    def stop_legacy_nat_instances(self):
        print 'Stopping old NAT instances..'
        for instance in self.convertable_nat_instances():
            instance_id = instance['InstanceId']
            print ' stopping instance {}'.format(instance_id)
            response = self.client.stop_instances(
                InstanceIds=[instance_id]
            )
        print ' ..done. (response={})'.format(response)

    def terminate_legacy_nat_instances(self):
        print 'Terminating old NAT instances..'
        for instance in self.convertable_nat_instances():
            instance_id = instance['InstanceId']
            print ' terminating instance {}'.format(instance_id)
            response = self.client.terminate_instances(
                InstanceIds=[instance_id]
            )
        print ' ..done. (response={})'.format(response)


if __name__ == '__main__':
    converter = NatConverter()
    try:
        converter.select_vpc()
    except VpcHasNatGatewayException:
        print
        print 'This VPC already has a NAT Gateway! Aborting..'
        exit()

    print
    print 'Convertable legacy NAT instances found on this VPC:'
    for instance in converter.convertable_nat_instances():
        print '  ', instance['InstanceId']

    print
    print "This VPC is validated and the AWS VPC NAT Gateway service can replace the existing legacy NAT instances."
    print
    print "If you choose to continue, the following actions will be performed:"
    print " 1. The following legacy NAT instance(s) will be stopped: "
    for instance in converter.convertable_nat_instances():
        print '  ', instance['InstanceId']

    print " 2. The following subnets' traffic will be routed to the NAT gateway:"
    for sub in converter.private_subnets():
        print '  ', sub

    print " 3. The NAT gateway will be deployed into one of the following subnets (you'll get to select which one):"
    for sub in converter.public_subnets():
        print '  ', sub['SubnetId']

    _input = raw_input('Do you wish to continue (Y/n): ')
    if _input.upper() != 'Y':
        print("Goodbye!")
        exit()

    _input = raw_input('Do you wish to associate an EIP with the new NAT Gateway (Y/n): ')
    if _input.upper() == 'Y':
        converter.allocate_elastic_ip()
        print('New EIP allocation id: {}'.format(converter.eip_allocation_id))

    nat_gateway_id = converter.create_nat_gateway()
    print 'New NAT Gateway instance created: {}'.format(nat_gateway_id)

    converter.wait_on_nat_gateways_ready(nat_gateway_id)
    converter.update_routing()

    print 'What would you like to do with the legacy NAT instances?'
    print '1. Stop them.'
    print '2. Terminate them.'
    print '3. Do nothing to them.'
    _input = int(raw_input('Enter your selection (1, 2 or 3): '))
    if _input == 1:
        converter.stop_legacy_nat_instances()
    elif _input == 2:
        converter.terminate_legacy_nat_instances()
    elif _input == 3:
        print 'Doing nothing to legacy NAT instances ({})'.format(
            ', '.join([instance['InstanceId'] for instance in converter.convertable_nat_instances()])
        )

    print 'Conversion complete!'

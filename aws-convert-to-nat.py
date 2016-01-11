import boto3
import time

client = boto3.client('ec2')

response = client.describe_vpcs()
vpcs = response['Vpcs']

if len(vpcs) == 0:
    print 'You have not VPCs in your account.'
    exit()

print 'Which VPC would you like to analyze:'

index = 1
for v in vpcs:
    name = v['VpcId'] + ' - ' + v['CidrBlock']
    if v['IsDefault'] == True:
        name = name + ' (Default VPC)'
    if 'Tags' in v:
        if 'Tags' in v:
            for t in v['Tags']:
                if t['Key'] == 'Name':
                    if len(t['Value']) > 0:
                        name = name + ' - ' + t['Value']
                    break
        # (item for item )
    print ('{0}:  ' + name).format(index)
    # print v
    index += 1

input_vpc = raw_input('Enter your number of VPC to analyze: ')

try:
   val = int(input_vpc)
except ValueError:
   print("That's not a valid VPC!1")

if int(input_vpc) < 1 or int(input_vpc) > len(vpcs):
    print("That's not a valid VPC!")
    exit()

working_vpcid = vpcs[int(input_vpc)-1]['VpcId']

response = client.describe_nat_gateways(Filter=[{'Name': 'vpc-id', 'Values': [working_vpcid]},{'Name': 'state', 'Values': ['available']}])

if len(response['NatGateways']) > 0:
    print 'NAT Gateway already exists.'
    exit()

response = client.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [working_vpcid]}])

print 'Getting Route Tables...'

current_nat_instances = []
public_subnets = []
private_subnets = []
private_route_tables = []

for a in response['RouteTables']:
    #print 'Route Table-' + a['RouteTableId'] + ':'
    current_routetable = a['RouteTableId']
    is_public = False
    for r in a['Routes']:
        #print 'Route:'
        #print r
        if 'GatewayId' in r:
            if r['DestinationCidrBlock'] == '0.0.0.0/0':
                is_public = True;
        if 'InstanceId' in r:
            #print r['InstanceId'] + ':' + r['DestinationCidrBlock']
            dict_to_add = {'RouteTableId': current_routetable, 'InstanceId':r['InstanceId'],'DestinationCidrBlock':r['DestinationCidrBlock']}
            current_nat_instances.append(dict_to_add.copy())
    for assoc in a['Associations']:
        #print 'Associations:'
        #print assoc
        if 'SubnetId' in assoc:
            #print assoc['SubnetId']
            if is_public == True:
                public_subnets.append(assoc['SubnetId'])
            else:
                private_subnets.append(assoc['SubnetId'])
    if is_public == False:
        private_route_tables.append(current_routetable)

#print current_nat_instances
cni_idx = 0
for c in current_nat_instances:
    response = client.describe_instance_attribute(InstanceId=c['InstanceId'],Attribute='sourceDestCheck')
    if response['SourceDestCheck']['Value'] == True:
        del current_nat_instances[cni_idx:]
    cni_idx += 1

if len(current_nat_instances) == 0:
    print 'There are no NAT instances to replace.  Goodbye!'
    exit()

print 'current nat instances:'
print current_nat_instances
print 'public subnets:'
print public_subnets
print 'private subnets: '
print private_subnets
print 'private route tables:'
print private_route_tables

print 'This VPC is validated and VPC NAT Gateway service can replace the legacy NAT instances.'
print 'The following will take place:'
print 'Instance ID(s) will be terminated: '
for instance in current_nat_instances:
    print instance['InstanceId']

print '\nThe following subnet''s traffic will be routed to the NAT gateway:'
for sub in private_subnets:
    print sub

print '\nThe NAT gateway will be deployed into one of the following subnets:'
for sub in public_subnets:
    print sub

input_continue = raw_input('Do you wish to continue (Y/n): ')

#try:
#   val = str(input_continue)
#except ValueError:
#   print("That's not a valid choice, goodbye!")

if input_continue != 'Y':
    print("Goodbye!")
    exit()

print 'Choose which public subnet to deploy the NAT gateway in:'
for sub in public_subnets:
    print sub
input_pub = raw_input('Type the name of the subnet ID: ')

deploy_subnet = str(input_pub)

input_public_EIP = raw_input('Do you wish to associate an EIP with the NAT Gateway (Y/n): ')

input_final = raw_input('Confirm you want to continue (Y/n): ')
if input_final != 'Y':
    print 'Nervous?'
    exit()

EIP_AllocationID = None

if input_public_EIP == 'Y':
    response = client.allocate_address(
        Domain='vpc'
    )
    print 'Allociating EIP...'
    EIP_AllocationID = response['AllocationId']

if EIP_AllocationID == None:
    print 'no EIP'
    response = client.create_nat_gateway(
        SubnetId='string'
    )
    print 'Create NAT Gateway...'
else:
    print 'EIP'
    response = client.create_nat_gateway(
        SubnetId=input_pub,
        AllocationId=EIP_AllocationID
    )
    print 'Create NAT Gateway w/EIP...'

NatGatewayId = response['NatGateway']['NatGatewayId']

for instance in current_nat_instances:
    print 'terminating:'
    print instance['InstanceId']
    response = client.terminate_instances(
        InstanceIds=[
            instance['InstanceId']
        ]
    )
    print 'Terminating Old NAT Instances....'
    # print response
    # remove old instance from routetables

    response = client.delete_route(
        RouteTableId=instance['RouteTableId'],
        DestinationCidrBlock=instance['DestinationCidrBlock']
    )
    print 'Deleting Old Routes...'
    # print response

NAT_Exists = False
while (NAT_Exists == False):
    response = client.describe_nat_gateways(
        NatGatewayIds=[
            NatGatewayId
        ]
    )
    # print 'describe_nat_gateways'
    # print response

    if len(response['NatGateways']) > 0:
        if response['NatGateways'][0]['State'] == 'available':
            NAT_Exists = True
    print 'waiting for NAT instance to start....'

    time.sleep(5)

for instance in current_nat_instances:
    response = client.create_route(
        RouteTableId=instance['RouteTableId'],
        DestinationCidrBlock=instance['DestinationCidrBlock'],
        NatGatewayId=NatGatewayId
    )
    print 'Creating Route Table Updates...'
    #print response

print 'Done!'
exit()

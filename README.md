# aws_nat_gateway_converter

I want to thank [Coin Graham](https://www.linkedin.com/in/coingraham) for inspiring me to do this.  It was really all his idea.  I just thought I would give it a try.

BETA:

This simple python application will make use of the [New AWS Managed NAT service](https://aws.amazon.com/blogs/aws/new-managed-nat-network-address-translation-gateway-for-aws/).  It will remove old NAT instances, cleanup the route tables, deploy a new NAT gateway, and update the route tables with the new Managed Service.  Optionally, there is the ability to allocate and EIP to the service.  

Requirements:
* python 2.7
* AWS CLI
* AWS boto3 library
* IAM keys with rights to VPC/EC2 - pretty much full rights
* run 'aws config' and put in key/secret

The MIT License (MIT)
Copyright (c) 2016 Ian B. Willoughby

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

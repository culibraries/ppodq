from celery.task import task
import os
import json
import requests
from requests.exceptions import Timeout, ConnectionError, HTTPError


@task(serializer='json')
def getDeliveryInfo(isbn):
    """
        Ask Oasis to provide book delivery info
        for given isbn.
    """

    # result that will return to caller/client 
    result = {
        'code': 0,
        'deliveryDays': -1,
        'deliveryDaysAdjusted': -1 
    }

    # Ensure we have an isbn
    if (isbn is None):
        return result

    # construct the url (without params)
    oasis_host = os.getenv('OASIS_HOST', None)
    oasis_api_key = os.getenv('OASIS_API_KEY', None)
    oasis_url = "https://{0}/stockcheck/".format(oasis_host)

    print(oasis_url);

    # Oasis stock check API requires our api key and the isbn number
    requestData = {
        'apiKey': oasis_api_key,
        'ISBN': isbn}

    # Call Oasis API that returns the delivery days for given ISBN.
    try:
        response = requests.get(
            oasis_url, 
            params=requestData, 
            timeout=(10, 20)
        )

        """
            Expecting to receive json in the form:
            {
               Environment: 'Development',
               RequestEnd: '/Date(1618604720623+0000)/',
               RequestStart: '/Date(1618604720266+0000)/',
               Code: 0,
               DeliveryDays: '14',
               Message: 'OASIS Accepts Orders'
            }
        """
        response_data = response.json()

        print(response.status_code)
        print("My response json:")
        print(response_data)

        # request was successfully received
        if (response.status_code == 200):
            result['code'] = response_data["Code"]

            # Oasis API sent a  successful response
            if (response_data["Code"] == 0):
                delivery_days = int(response_data["DeliveryDays"])
                result['deliveryDays'] = delivery_days 

                # calculate the adjusted delivery days
                if (delivery_days < 5):
                    result['deliveryDaysAdjusted'] = 18
                else:
                    result['deliveryDaysAdjusted'] = delivery_days + 4 
            # Oasis API responded with a failure
            else:
                result['code'] = 400
        else:
            result['code'] = response.status.code 

    # Handle all common errors that could occur with request
    except Timeout as err:
        print(err)
        result['code'] = 408
    except (ConnectionError, HTTPError) as err:
        print(err)
        result['code'] = 400

    # return our result
    return result

@task(serializer='json')
def submitOrder(idKey, form_data):
    """
        Submit book order to Oasis API, email patron and staff,
        and log event in DB. 
    """

    # result that will return to caller/client 
    result = {
        'code': 0,
        'message': ''
    }

    # return our result
    return result
    

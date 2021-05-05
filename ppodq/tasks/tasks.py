from celery.task import task
import os
import requests
from requests.exceptions import Timeout, ConnectionError, HTTPError
from enum import Enum


########  ENV VARIABLES  ########
OASIS_HOST = os.getenv('OASIS_HOST')
OASIS_API_KEY = os.getenv('OASIS_API_KEY')
TOKEN = os.getenv('PPOD_SYSTEM_TOKEN')
REPLY_EMAIL = os.getenv('REPLY_EMAIL_ADDRESS')
STAFF_EMAIL = os.getenv('STAFF_EMAIL_ADDRESS')
EMAIL_URL = os.getenv('EMAIL_URL')

######## GLOBAL CONSTANTS  ########
REQUEST_TIMEOUT = (15, 21) # connection and read timeouts in seconds

"""
Types of emails that can be sent by ppod:
    1 - confirmation email sent to patron
    2 - regular delivery order notification sent to staff 
    3 - rush delivery order notification sent to staff 
    4 - order error notification sent to staff 
"""
class PPOD_EMAIL_TYPE(Enum):
    CONFIRMATION_TO_PATRON = 1
    REGULAR_ORDER_NOTICE = 2
    RUSH_ORDER_NOTICE = 3
    ERROR_ORDER_NOTICE = 4


########  TASKS  ########  

@task(serializer='json')
def getDeliveryInfo(isbn):
    """
    Ask Oasis to provide book delivery info
    for given isbn.
    args: isbn
    kwargs: {}
    """

    # result that will return to caller/client 
    result = {
        'code': 0,
        'deliveryDays': -1,
        'deliveryDaysAdjusted': -1
    }

    # ensure we have an isbn
    if (isbn is None):
        result["code"] = 400
        return result

    # construct the url (without params)
    oasis_url = "https://{0}/stockcheck/".format(OASIS_HOST)

    # Oasis stock check API requires our api key and the isbn number
    requestData = {
        'apiKey': OASIS_API_KEY,
        'ISBN': isbn}

    # Call Oasis API that returns the delivery days for given ISBN.
    try:
        response = requests.get(
            oasis_url,
            params = requestData,
            timeout = REQUEST_TIMEOUT)

        """
        Expecting to receive json with items:
           Environment: 'Development',
           RequestEnd: '/Date(1618604720623+0000)/',
           RequestStart: '/Date(1618604720266+0000)/',
           Code: 0,
           DeliveryDays: '14',
           Message: 'OASIS Accepts Orders'
        """
        response_data = response.json()

        # request was successfully received
        if (response.status_code == 200):
            result['code'] = response_data["Code"]

            # Oasis API sent a successful response
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
    PPOD submit book order and notify patron and staff via email. 
    Submitting an order will trigger the book to be ordered via OASIS API
    only if the delivery type is not a rush order.
    args: identiKey
    kwargs: form_data={first_name, last_name, email, 
        department, affiliation, title, author, isbn,
        delivery_days, delivery_days_adjusted, delivery_type}
    """

    # result to return to caller/client 
    result = {
        'code': 0,
        'message': ''
    }

    # TODO - form data validation
    if form_data["delivery_type"] not in ["rush", "regular"]:
        result["code"] = 400
        result.message = "Invalid Delivery Type"
        return result


    # TODO - Insert into DB 


    # Setup and send an order confirmation email to patron
    email_setting = setupEmail(PPOD_EMAIL_TYPE.CONFIRMATION_TO_PATRON,
                               form_data["email"], form_data)
    try:
        response = requests.post(
            email_setting["url"],
            json = email_setting["post_data"],
            headers = email_setting["headers"],
            timeout = REQUEST_TIMEOUT)

    # handle errors for sending email to patron by logging it
    except (Timeout, ConnectionError, HTTPError) as err:
        # Log request errors
        print(err)

    # For rush orders, email the staff but do NOT order book
    if (form_data["delivery_type"] == "rush"):
        email_setting = setupEmail(PPOD_EMAIL_TYPE.RUSH_ORDER_NOTICE,
                                   form_data["email"], form_data)
        try:
            response = requests.post(
                email_setting["url"],
                json = email_setting["post_data"],
                headers = email_setting["headers"],
                timeout = REQUEST_TIMEOUT)

            # TODO - poll the returned url to check status

        # handle errors for sending email to staff by logging it
        except (Timeout, ConnectionError, HTTPError) as err:
            # Log request errors
            print(err)

    # For regular orders, place the order with OASIS and email staff
    else:
        # TODO - Order the book first then poll request to inform staff 
        #        of any errors 
        email_setting = setupEmail(PPOD_EMAIL_TYPE.REGULAR_ORDER_NOTICE,
                                   form_data["email"], form_data)
        try:
            response = requests.post(
                email_setting["url"],
                json = email_setting["post_data"],
                headers = email_setting["headers"],
                timeout = REQUEST_TIMEOUT)

        # handle errors for sending email to staff by logging it
        except (Timeout, ConnectionError, HTTPError) as err:
            # Log request errors
            print(err)


    # return our result
    return result


########  HELPER FUNCTIONS  ########  

def setupEmail(email_type, patron_email, email_data):
    """
    Return the email post data, header, and url for given 
    email type as defined by PPOD_EMAIL_TYPE enum.
    Depends on the following globals set by environment variables:
        REPLY_EMAIL, STAFF_EMAIL, EMAIL_URL, TOKEN,
    Returns {post_data, headers, url}
    """

    # these may not all be used in every ppod email template
    template_data = {
        "title": email_data["title"],
        "author": email_data["author"],
        "isbn": email_data["isbn"],
        "name": email_data["first_name"] + " " + email_data["last_name"],
        "affiliation": email_data["affiliation"],
        "department": email_data["department"],
        "email": email_data["email"],
        "delivery": email_data["delivery_type"],
        "delivery_days": email_data["delivery_days_adjusted"]
    }

    # Set the recipient, subject, and email template based on ppod email type
    if (email_type == PPOD_EMAIL_TYPE.CONFIRMATION_TO_PATRON):
        recipient_email = patron_email
        subject = "Print Purchase on Demand Order"
        email_template = "ppod_order_confirmation.html.j2"
    else:
        recipient_email = STAFF_EMAIL
        email_template = "ppod_staff_notification.html.j2"

        if (email_type == PPOD_EMAIL_TYPE.REGULAR_ORDER_NOTICE):
            subject = "PPOD order ready for approval"
        elif (email_type == PPOD_EMAIL_TYPE.RUSH_ORDER_NOTICE):
            subject = "PPOD rush order"
        elif (email_type == PPOD_EMAIL_TYPE.ERROR_ORDER_NOTICE):
            subject = "PPOD Error in Order"
            # change to indicate error with order
            template_data["delivery"] = "error"
        else:
            subject = "Print Purchase on Demand Order"

    # compose the email request post data
    post_data = {
        "queue": "celery",
        "args": [recipient_email, REPLY_EMAIL, subject],
        "kwargs": {
            "template": email_template,
            "template_data": template_data},
        "tags": []}

    # The header requires authorization via token
    headers = {"Authorization": "Token {0}".format(TOKEN)}

    return {
        "post_data": post_data,
        "headers": headers,
        "url": EMAIL_URL}

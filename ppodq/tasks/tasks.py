from celery.task import task
import os
import requests
from requests.exceptions import Timeout, ConnectionError, HTTPError
from enum import Enum
from datetime import datetime, timezone


########  ENV VARIABLES  ########
OASIS_HOST = os.getenv('OASIS_HOST')
OASIS_API_KEY = os.getenv('OASIS_API_KEY')
TOKEN = os.getenv('PPOD_SYSTEM_TOKEN')
REPLY_EMAIL = os.getenv('REPLY_EMAIL_ADDRESS')
STAFF_EMAIL = os.getenv('STAFF_EMAIL_ADDRESS')
EMAIL_URL = os.getenv('EMAIL_URL')
DB_URL = os.getenv('DB_URL')

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
def getDeliveryInfo(id_key, isbn):
    """
    Ask Oasis to provide book delivery info
    for given isbn.
    args: isbn
    kwargs: {}
    """

    # ensure we have an authenticated user
    if getDeliveryInfo.request.authenticated_user.get('username') != id_key:
        raise RuntimeError("Not Authorized")

    # result that will return to caller/client 
    result = {
        'code': 0,
        'message': '',
        'deliveryDays': -1,
        'deliveryDaysAdjusted': -1
    }

    # ensure we have an isbn
    if (isbn is None):
        result["code"] = 400
        return result

    """
    Expecting to receive back from OASIS the following fields
    of which we only care about the last three:
       Environment: 'Development',
       RequestEnd: '/Date(1618604720623+0000)/',
       RequestStart: '/Date(1618604720266+0000)/',
       Code: 0,
       DeliveryDays: '14',
       Message: 'OASIS Accepts Orders'
    """
    response = callOasisAPI("stockcheck", isbn)

    if response["status_code"] == 200:
        response_data = response["response_json"]

        # save the code returned by the API
        result["code"] = response_data["Code"]

        # Oasis API sent a successful response
        if response_data["Code"] == 0:
            delivery_days = int(response_data["DeliveryDays"])
            result['deliveryDays'] = delivery_days

            # calculate the adjusted delivery days
            if (delivery_days < 5):
                result['deliveryDaysAdjusted'] = 18
            else:
                result['deliveryDaysAdjusted'] = delivery_days + 18
        else:
            result["message"] = response_data["Message"]
    else:
        result["code"] = response["status_code"]
        result["message"] = response_data["Message"]

    # return our result
    return result


@task(serializer='json')
def submitOrder(id_key, form_data):
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

    # ensure we have an authenticated user
    if submitOrder.request.authenticated_user.get('username') != id_key:
        raise RuntimeError("Not Authorized")

    # check we have all the required form data
    if not all(k in form_data for k in 
        ("first_name", "last_name", "email",
         "department", "affiliation", "title", "author", "isbn",
         "delivery_days", "delivery_days_adjusted", "delivery_type")):
        result["code"] = 400
        result["message"] = "Missing required form data"
        return result

    # further validate the delivery type is valid 
    if form_data["delivery_type"] not in ["rush", "regular"]:
        result["code"] = 400
        result["message"] = "Invalid delivery choice"
        return result

    # ensure we have values for specific form data
    if (not form_data["isbn"] or
        not form_data["delivery_days_adjusted"] or
        not form_data["first_name"] or
        not form_data["last_name"] or
        not form_data["email"]):
        result["code"] = 400
        result["message"] = "Missing required form data"
        return result

    # Insert order request in DB 
    response = recordBookOrder(id_key, form_data)

    # Setup and email an order confirmation to patron
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
            # let client know we could not process submit
            result["code"] = 500
            result["message"] = "Unable to notify library staff"

    # For regular orders, place the order with OASIS and email staff
    else:
        successful_order = False 

        """
        Expecting to receive back from OASIS the following fields
        of which we only care about the last two::
           Environment: 'Development',
           RequestEnd: '/Date(1618604720623+0000)/',
           RequestStart: '/Date(1618604720266+0000)/',
           OrderNumber: '',
           Code: 100,
           Message: 'Success'
        """
        response = callOasisAPI("order", form_data["isbn"])

        #
        # Successful request
        # If the request was not successful, we will just
        # inform the staff via email and not return error
        # to client so that they do not continue to submit
        # the order multiple times.
        #
        if response["status_code"] == 200:
            response_data = response["response_json"]

            result["message"] = response_data["Message"]

            # Oasis API sent a successful response
            if response_data["Code"] == 100:
                successful_order = True
                result["code"] = 0 

            # Oasis API did not recognize ISBN
            #elif response_data["Code"] == 200:
                #result["code"] = 400

            # Oasis API general error 
            #else:
            #   result["code"] = response_data["Code"] 

        # determing if staff gets order notification email or error notice 
        if successful_order:
            email_setting = setupEmail(PPOD_EMAIL_TYPE.REGULAR_ORDER_NOTICE,
                                       form_data["email"], form_data)
        else:
            email_setting = setupEmail(PPOD_EMAIL_TYPE.ERROR_ORDER_NOTICE,
                                       form_data["email"], form_data)

        # send email to staff about the order
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

            # the client needs to be notified that their book order
            # failed and the staff was not notified of the error
            if not successful_order:
                result["code"] = 500


    # return our result
    return result


########  HELPER FUNCTIONS  ########

def recordBookOrder(id_key, db_data):

    # construct the DB url with DB name
    url = "{0}{1}/".format(DB_URL, 'ppod')

    # the header requires authorization via token
    headers = {"Authorization": "Token {0}".format(TOKEN)}

    current_datetime = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

    # store all the form data plus current timestamp
    post_data = {
        "username": id_key,
        "first_name": db_data["first_name"],
        "last_name": db_data["last_name"],
        "email": db_data["email"],
        "department": db_data["department"],
        "affiliation": db_data["affiliation"],
        "title": db_data["title"],
        "author": db_data["author"],
        "isbn": db_data["isbn"],
        "delivery_days": db_data["delivery_days"],
        "delivery_days_adjusted": db_data["delivery_days_adjusted"],
        "delivery_type": db_data["delivery_type"],
        "create_datetime": current_datetime}

    try:
        response = requests.post(
            url,
            json = post_data,
            headers = headers,
            timeout = REQUEST_TIMEOUT)

    # handle errors for sending email to staff by logging it
    except (Timeout, ConnectionError, HTTPError) as err:
        # Log request errors
        print(err)


def callOasisAPI(api_end_point, isbn):

    # returning item initialized 
    result = {
        "status_code": 200,
        "response_json": {} 
    }

    # construct the url (without params)
    oasis_url = "https://{0}/{1}".format(OASIS_HOST, api_end_point)

    # Oasis stock check API requires our api key and the isbn number
    requestData = {
        "apiKey": OASIS_API_KEY,
        "ISBN": isbn
    }

    # order api endpoint has two other params
    if (api_end_point == 'order'):
        requestData["Quantity"] = 1
        requestData["Dupeover"] = "false"

    # Call ProQuest Oasis API which returns the delivery days for given ISBN
    try:
        response = requests.get(
            oasis_url,
            params = requestData,
            timeout = REQUEST_TIMEOUT)

        result["status_code"] = response.status_code

        # request was successfully received
        if (response.status_code == 200):
            # as long as the request came back without error we are good..
            # It will be the caller's responsiblity to check endpoint status 
            result["response_json"] = response.json()

    # Handle all common errors that could occur with request
    except Timeout as err:
        print(err)
        result["status_code"] = 408
    except (ConnectionError, HTTPError) as err:
        print(err)
        result['statu_code'] = 400

    return result


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

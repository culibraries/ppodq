from celery.task import task
import os
import requests


#Example task
@task()
def add(x, y):
    """ Example task that adds two numbers or strings
        args: x and y
        return addition or concatination of strings
    """
    result = x + y
    return result


@task()
def getDeliveryInfo(isbn):
    """ Example task
        return book info 
    """
    oasis_url= os.getenv('OASIS_URL',None)
    # req= request.get(oasis_url)
    # data=req.json()
    return isbn
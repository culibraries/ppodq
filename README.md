ppodq Queue
======================

Print Purchase On Demand APIs.  
Used by the Print Purchase web form to get estimated book delivery info
and submit a book order. 


Requirements
------------
1. CU authenticated user.
2. emailCULibq task.
3. MongoDB data catalog.
4. Account with ProQuest Oasis and an API Key.
5. Cybercommons API and Task Queue.
6. A new group where all authenticated users who need to use ppod are a member.  This new group will need access to the cybercom queue tasks getDeliveryInfo and submitOrder (defined in this repo).
7. A new ppod user with permission to ADD/UPDATE to the ppod data catalog and permission to run emailCULibq task.
8. update `cybercom` secret to add ppodq to `SAFE_METHOD_PERM_REQUIRED`, `CELERY_IMPORTS` and `CELERY_SOURCE`.
9. The following environmental variables are required: 
    OASIS_HOST : ProQuest Oasis hostname
    OASIS_API_KEY : CU's ProQuest Oasis API Key string
    TOKEN : ppod system user's token to use for email and DB
    REPLY_EMAIL : reply email address to use for both patron and staff emails
    STAFF_EMAIL : email address to send staff notifications
    EMAIL_URL : complete URL for email task
    DB_URL : complete URL for MongoDB catalog


Dependencies
------------

The following are dependencies:
1. python request module


License
-------


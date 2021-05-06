ppodq Queue
======================

Print Purchase On Demand APIs.  This includes two APIs

Requirements
------------
1 - authenticated user
2 - sendEmail task
3 - MongoDB data catalog
4 - Account with ProQuest Oasis and an API Key 

The following environmental variables are required: 
    OASIS_HOST : ProQuest Oasis hostname
    OASIS_API_KEY : CU's ProQuest Oasis API Key string
    TOKEN : ppod system user's token to use for email and DB
    REPLY_EMAIL : reply email address to use for both patron and staff emails
    STAFF_EMAIL : email address to send staff notifications
    EMAIL_URL : complete URL for email task
    DB_URL : complete URL for MongoDB catalog


Dependencies
------------

The following are dependencis:
1 - python request module

A list of other dependencies need to run queue tasks.


License
-------


Author Information
------------------

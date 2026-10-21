# Spec for theater app backend

You are trying to build the backend for the theater app outlined in readme.md. Read it to understand the context, but read this document in it's entirety for the primary instructions where i have provided more specifics. The stack for this is going to be next/react for front end (aready implemented), fast api (stubs only), and use supabase postgres for our database. The remote db is in the env file, but for local debugging we should use the local supabase + docker. Assume the remote project is empty so we must create all the sql migration scripts as well.

Non functional requirements:
- Users must have roles. Users can be admin, who has full read/write access. Non admin can only read.
- Admin can update movie status field that non admins cannot complete
- Users also can access certain theaters, this is independent of the admin role. We should also have a role that allows a user to view all theaters, instead of a specific list.
- For scope of this, do not implement a login/auth system.
- User should be able to search for movies, using movie name, filters, and be able to sort by name (A-Z, Z-A) and showtime (soonest-latest and vice versa)
- Admin should be able to upload CSV to add new data. It should be converted into postgres table as defined below in our entity schemas
- Schedules should per persisted in the database, and missing showtimes should be archived and flagged for admin review.

APIs:

POST uploadshowtime/ -> uploading csv to database 201
body: csv

GET movies/ -> return list of showtimes, limited to 50 per page
query parameters: status, format, language, rating, movie status (only admin can sort by this, defualt user can see only approved), startdate, enddate, auditoriums, theater
header - user role

POST clear schedule -> archives all movies for a selected theater

Datamodels:

User
id uuid -> pk
name varchar
email varchar
role enum (admin, user)
canViewAll bool
theaterIds uuids -> fk

Theater
id uuid
name varchar
location varchar
timezone varchar

Movies
id
title varchar
language
rating

Showtime
id
movie_id -> fk
theater_id -> fk
starttime datetime
endtime datetime
status enum
format
lastupdated

please read the schema, and make it work end to end. ask any ambiguities before building the prototype end to end.
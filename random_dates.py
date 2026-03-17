import random
import datetime

start = datetime.datetime(2026, 3, 16, 0, 0, 0)
end   = datetime.datetime(2026, 3, 17, 23, 59, 59)
delta = int((end - start).total_seconds())
secs  = random.randint(0, delta)
dt    = start + datetime.timedelta(seconds=secs)
ts    = int(dt.timestamp())

# Use +0700 since you're in HCMC (+07 timezone) – looks more legit/local
# Change to +0000 if you want pure UTC
tz_offset = b' +0700'

new_date = (str(ts) + tz_offset.decode()).encode()

commit.author_date    = new_date
commit.committer_date = new_date
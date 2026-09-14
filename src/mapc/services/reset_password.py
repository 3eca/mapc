from getpass import getpass

from argon2 import PasswordHasher

p = getpass("New password: ")
q = getpass("Confirm password: ")

if p == q and len(p) >= 5:
    print(PasswordHasher().hash(p))
else:
    print("Passwords do not match or are shorter than 5 characters")

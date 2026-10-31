# Email accounts

Create an account using your name, email address and a password of at least 10 characters. Sign in with the same email and password.

Accounts and query history persist in the PostgreSQL metadata database in the Docker `pgdata` volume. Passwords use salted scrypt hashes; session tokens are stored as hashes and expire after seven days. Signing out revokes the current session.

Business data is shared by registered users. Query archives and feedback are private to each account. Existing database records are retained.

Sessions stay in Streamlit server-side session state. A browser reload that starts a new Streamlit session may require sign-in again. Email verification, password reset and persistent remember-me cookies are not implemented.

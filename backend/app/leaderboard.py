
def rank_users(users):
    """Rank users by total XP, highest first."""
    sorted_users = sorted(
        users,
        key=lambda user: user["total_xp"],
        reverse=True
    )

    leaderboard = []
    previous_xp = None
    current_rank = 0

    for position, user in enumerate(sorted_users, start=1):
        if user["total_xp"] != previous_xp:
            current_rank = position

        leaderboard.append({
            "rank": current_rank,
            "user_id": user["user_id"],
            "total_xp": user["total_xp"],
            "level": user["level"]
        })

        previous_xp = user["total_xp"]

    return leaderboard



def generate_feedback(score, level):
    if score >= 80:
        reward = 1.0
        msg = "Excellent understanding. You can move to higher difficulty."
    elif score >= 50:
        reward = 0.5
        msg = "Good attempt, but try to include more key points."
    else:
        reward = -0.5
        msg = "Answer lacks depth. Review concepts and try again."

    return {
        "score": score,
        "reward": reward,
        "message": msg,
        "next_level": adaptive_level(level, reward)
    }


def adaptive_level(current, reward):
    levels = ["easy", "medium", "hard"]
    idx = levels.index(current)

    if reward > 0 and idx < 2:
        return levels[idx + 1]
    elif reward < 0 and idx > 0:
        return levels[idx - 1]

    return current

def classify_text(text: str):
    l = text.lower()

    if "ourfamilywizard" in l or "wizard" in l:
        return "OFW"
    if "mcfd" in l or "child safety" in l:
        return "MCFD"
    if "family maintenance" in l or "bcfma" in l:
        return "BCFMA"
    if "imessage" in l or "sms" in l:
        return "TEXTLOG"
    return "UNSORTED"

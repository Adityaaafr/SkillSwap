"""Turns members' profile locations into data for the swap map on the home page.

Locations are free text, so we match the part before the first comma against a small table of
Indian cities. Members in other places simply don't appear on the map.
"""
from accounts.models import Profile
from exchange.models import ExchangeRequest

# key: (label, latitude, longitude)
CITIES = {
    "agra": ("Agra", 27.18, 78.01), "ahmedabad": ("Ahmedabad", 23.02, 72.57),
    "amritsar": ("Amritsar", 31.63, 74.87), "bengaluru": ("Bengaluru", 12.97, 77.59),
    "bangalore": ("Bengaluru", 12.97, 77.59), "bhopal": ("Bhopal", 23.26, 77.41),
    "bhubaneswar": ("Bhubaneswar", 20.30, 85.82), "chandigarh": ("Chandigarh", 30.73, 76.78),
    "chennai": ("Chennai", 13.08, 80.27), "coimbatore": ("Coimbatore", 11.02, 76.96),
    "dehradun": ("Dehradun", 30.32, 78.03), "delhi": ("Delhi", 28.61, 77.21),
    "new delhi": ("Delhi", 28.61, 77.21), "goa": ("Goa", 15.49, 73.83),
    "gurugram": ("Gurugram", 28.46, 77.03), "gurgaon": ("Gurugram", 28.46, 77.03),
    "guwahati": ("Guwahati", 26.14, 91.74), "hyderabad": ("Hyderabad", 17.39, 78.49),
    "indore": ("Indore", 22.72, 75.86), "jaipur": ("Jaipur", 26.91, 75.79),
    "jalandhar": ("Jalandhar", 31.33, 75.58), "jamshedpur": ("Jamshedpur", 22.80, 86.20),
    "kanpur": ("Kanpur", 26.45, 80.33), "kochi": ("Kochi", 9.93, 76.27),
    "kolkata": ("Kolkata", 22.57, 88.36), "lucknow": ("Lucknow", 26.85, 80.95),
    "ludhiana": ("Ludhiana", 30.90, 75.85), "mumbai": ("Mumbai", 19.08, 72.88),
    "mysuru": ("Mysuru", 12.30, 76.64), "mysore": ("Mysuru", 12.30, 76.64),
    "nagpur": ("Nagpur", 21.15, 79.09), "noida": ("Noida", 28.54, 77.39),
    "patna": ("Patna", 25.59, 85.14), "pune": ("Pune", 18.52, 73.86),
    "ranchi": ("Ranchi", 23.34, 85.31), "surat": ("Surat", 21.17, 72.83),
    "thiruvananthapuram": ("Thiruvananthapuram", 8.52, 76.94), "trivandrum": ("Thiruvananthapuram", 8.52, 76.94),
    "vadodara": ("Vadodara", 22.31, 73.18), "varanasi": ("Varanasi", 25.32, 82.97),
    "visakhapatnam": ("Visakhapatnam", 17.69, 83.22),
}


def city_key(location):
    """'Pune, Maharashtra' -> 'pune' if we know it, else None."""
    key = (location or "").split(",")[0].strip().lower()
    if key not in CITIES:
        return None
    return CITIES[key][0].lower()  # merge aliases such as Bangalore/Bengaluru (every label is also a key)


def swap_map_data():
    """{'points': [...], 'routes': [[a, b], ...]} for the signal map, built from real data."""
    city_of, points = {}, {}
    for user_id, location in Profile.objects.filter(user__is_active=True).exclude(location="").values_list(
        "user_id", "location"
    ):
        key = city_key(location)
        if not key:
            continue
        label, lat, lng = CITIES[key]
        city_of[user_id] = key
        point = points.setdefault(key, {"id": key, "label": label, "lat": lat, "lng": lng, "members": 0, "swaps": 0})
        point["members"] += 1

    routes = set()
    live = ExchangeRequest.objects.exclude(
        status__in=[ExchangeRequest.Status.REJECTED, ExchangeRequest.Status.CANCELLED]
    ).values_list("sender_id", "receiver_id")
    for sender_id, receiver_id in live:
        a, b = city_of.get(sender_id), city_of.get(receiver_id)
        if a and b and a != b:
            routes.add(tuple(sorted((a, b))))
            points[a]["swaps"] += 1
            points[b]["swaps"] += 1

    ordered = sorted(points.values(), key=lambda p: (-p["members"], -p["swaps"], p["label"]))
    return {"points": ordered, "routes": [list(r) for r in sorted(routes)]}

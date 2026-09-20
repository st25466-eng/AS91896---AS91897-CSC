import json, os
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = "superdupersuperkey"  
DATA_FILE = "data.json"

# --- HELPER FUNCTIONS ---

def get_data(key=None):
    """Loads JSON data safely and optionally returns a specific top-level key."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                return data.get(key, []) if key else data
        except json.JSONDecodeError: pass
    return [] if key else {"users": [], "bakeries": []}

def save_data(data):
    """Saves the main data dictionary back to data.json."""
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def require_owner():
    """Security check: Ensures only Bakery Owners can perform admin actions."""
    if session.get("account_type") != "Bakery Owner":
        flash("Only registered bakery owners can perform this action.", "error")
        return False
    return True

def validate_prices(prices):
    """Validates that all submitted item prices are numbers >= $1.00."""
    try:
        if any(float(p) < 1.00 for p in prices if p.strip()):
            flash("Item prices must be at least $1.00.", "error")
            return False
        return True
    except ValueError:
        flash("Please enter valid numbers for item prices.", "error")
        return False

def parse_items(names, prices, specials, base_id):
    """Converts form inputs into structured item dictionaries with dietary tags."""
    items = []
    for i, name in enumerate(names):
        if name.strip():
            base_id += 1
            price = float(prices[i]) if i < len(prices) and prices[i] else 1.00
            items.append({
                "id": base_id,
                "name": name.strip(),
                "price": round(price, 2),
                # Grabs dynamic dietary checkboxes (item_dietary_0, item_dietary_1, etc.)
                "dietary": request.form.getlist(f"item_dietary_{i}"),
                "special": str(i) in specials
            })
    return items, base_id


# --- ROUTE HANDLERS ---

@app.route("/")
def home():
    """Home page route."""
    return render_template("home.html")

@app.route("/bakeries")
def bakeries():
    """Renders the main storefront grid displaying all bakeries and products."""
    return render_template("bakeries.html", bakeries=get_data("bakeries"))

@app.route("/add_bakery", methods=["GET", "POST"])
def add_bakery():
    """Allows bakery owners to register a new bakery and its initial menu."""
    if not require_owner(): return redirect(url_for("bakeries"))
    
    if request.method == "POST":
        names, prices = request.form.getlist("item_names[]"), request.form.getlist("item_prices[]")
        if not request.form.get("bakery_name") or not names or not validate_prices(prices):
            return render_template("add_bakery.html")

        data = get_data()
        # Generate new auto-incremented bakery ID
        new_id = max([b["id"] for b in data["bakeries"]], default=0) + 1
        products, _ = parse_items(names, prices, request.form.getlist("item_specials[]"), new_id * 100)

        # Append new bakery object
        data["bakeries"].append({
            "id": new_id,
            "name": request.form.get("bakery_name"),
            "location": request.form.get("location"),
            "closing_time": request.form.get("closing_time"),
            "image": request.form.get("image_url") or "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop",
            "products": products
        })
        save_data(data)
        flash(f"'{request.form.get('bakery_name')}' added successfully!", "success")
        return redirect(url_for("bakeries"))
        
    return render_template("add_bakery.html")

@app.route("/bakery/<int:bakery_id>/add_item", methods=["POST"])
def add_item_to_bakery(bakery_id):
    """Allows bakery owners to add menu items directly to an existing bakery card."""
    if not require_owner(): return redirect(url_for("bakeries"))
    
    names, prices = request.form.getlist("item_names[]"), request.form.getlist("item_prices[]")
    if not names or not names[0].strip() or not validate_prices(prices):
        return redirect(url_for("bakeries"))

    data = get_data()
    # Find matching bakery by ID
    bakery = next((b for b in data["bakeries"] if b["id"] == bakery_id), None)
    if bakery:
        max_id = max([p["id"] for p in bakery.get("products", [])], default=bakery_id * 100)
        new_items, _ = parse_items(names, prices, request.form.getlist("item_specials[]"), max_id)
        bakery["products"] = bakery.get("products", []) + new_items
        save_data(data)
        flash(f"Added item(s) to '{bakery['name']}'!", "success")
        
    return redirect(url_for("bakeries"))

@app.route("/delete_item/<int:bakery_id>/<int:item_id>", methods=["POST"])
def delete_item(bakery_id, item_id):
    """Deletes a specific product from a bakery's menu list."""
    if not require_owner(): return redirect(url_for("bakeries"))
    
    data = get_data()
    for bakery in data["bakeries"]:
        if bakery["id"] == bakery_id:
            original_len = len(bakery.get("products", []))
            # Keep all items except the one matching item_id
            bakery["products"] = [p for p in bakery.get("products", []) if p["id"] != item_id]
            if len(bakery["products"]) < original_len:
                save_data(data)
                flash("Item successfully deleted.", "success")
            break
            
    return redirect(url_for("bakeries"))

@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    """Adds a item and chosen quantity to the user's session cart (Max limit: 20)."""
    b_id, i_id = request.form.get("bakery_id", type=int), request.form.get("item_id", type=int)
    qty = request.form.get("quantity", 1, type=int)

    if not (1 <= qty <= 20):
        flash("Invalid quantity! Must order between 1 and 20.", "error")
        return redirect(url_for("bakeries"))

    bakeries_list = get_data("bakeries")
    bakery = next((b for b in bakeries_list if b["id"] == b_id), None)
    item = next((i for i in bakery.get("products", []) if i["id"] == i_id), None) if bakery else None

    if bakery and item:
        cart = session.setdefault("cart", [])
        # If item is already in cart, update quantity
        for c in cart:
            if c["item_id"] == i_id and c["bakery_id"] == b_id:
                if c["quantity"] + qty > 20:
                    flash("Maximum limit of 20 per item reached!", "error")
                    return redirect(url_for("bakeries"))
                c["quantity"] += qty
                session.modified = True
                flash(f"Added {qty}x '{item['name']}' to cart!", "success")
                return redirect(url_for("bakeries"))

        # Add new item row to cart
        cart.append({
            "bakery_id": b_id, 
            "bakery_name": bakery["name"], 
            "item_id": i_id, 
            "item_name": item["name"], 
            "price": item["price"], 
            "special": item.get("special", False), 
            "quantity": qty
        })
        session.modified = True
        flash(f"Added {qty}x '{item['name']}' to cart!", "success")
        
    return redirect(url_for("bakeries"))

@app.route("/remove_from_cart/<int:index>")
def remove_from_cart(index):
    """Removes a specific line item from cart using its index."""
    cart = session.get("cart", [])
    if 0 <= index < len(cart):
        removed = cart.pop(index)
        session.modified = True
        flash(f"Removed '{removed['item_name']}' from cart.", "success")
    return redirect(url_for("checkout"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    """Displays shopping cart summary and processes order completion."""
    cart = session.get("cart", [])
    total = sum(round(i["quantity"] * i["price"], 2) for i in cart)
    
    if request.method == "POST":
        if not cart:
            flash("Your cart is empty!", "error")
            return redirect(url_for("bakeries"))
        session.pop("cart", None) # Clear cart on successful checkout
        flash(f"Order placed! Total: ${total:.2f}. Thank you!", "success")
        return redirect(url_for("bakeries"))
        
    return render_template("checkout.html", cart=cart, grand_total=total)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Handles user account registration (Customer vs Bakery Owner)."""
    if request.method == "POST":
        u = request.form.get("username")
        e = request.form.get("email")
        p = request.form.get("password")
        acc = request.form.get("account_type", "Customer")
        
        if not u or not e or not p:
            flash("Please fill in all fields.", "error")
            return render_template("signup.html")

        data = get_data()
        if any(user["email"] == e for user in data["users"]):
            flash("Email already registered. Please log in.", "error")
            return redirect(url_for("login"))

        data["users"].append({"username": u, "email": e, "password": p, "account_type": acc})
        save_data(data)
        flash(f"Welcome {u}! Account created.", "success")
        return redirect(url_for("login"))
        
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Authenticates credentials against JSON users and sets session state."""
    if request.method == "POST":
        user = next((u for u in get_data("users") if u["email"] == request.form.get("email") and u["password"] == request.form.get("password")), None)
        if user:
            session.update({"user": user["email"], "username": user["username"], "account_type": user["account_type"]})
            flash("Logged in successfully!", "success")
            return redirect(url_for("add_bakery" if user["account_type"] == "Bakery Owner" else "bakeries"))
        flash("Invalid email or password.", "error")
        
    return render_template("login.html")

@app.route("/logout")
def logout():
    """Logs out user by clearing the session data."""
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)
# Add this route to app.py, alongside your other /admin routes (e.g. near enquiries_list).
# Also add: import analytics  (near your other imports, alongside chat_store etc.)

@app.route('/admin/analytics')
@login_required
def analytics_dashboard():
    db = get_db()
    try:
        analytics.init_analytics_table(db)
        summary = analytics.get_summary(db, enquiries_store)
    finally:
        db.close()
    return render_template('analytics.html', summary=summary)

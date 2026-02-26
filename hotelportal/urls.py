from django.urls import path
from . import views
from django.urls import path
from . import views_live  # NEW file below
from . import views_billing
from . import consumers





urlpatterns = [
    path("", views.portal_home, name="portal_home"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/add/", views.staff_add, name="staff_add"),

     # rooms (Day 3.1)
    path("rooms/", views.rooms_list, name="rooms_list"),
    path("rooms/add/", views.room_create, name="room_create"),
    path("rooms/<int:pk>/edit/", views.room_edit, name="room_edit"),
    path("rooms/<int:pk>/delete/", views.room_delete, name="room_delete"),
    path("rooms/qr/print/", views.rooms_qr_sheet, name="rooms_qr_sheet"),
    # 3.3C — Settings route
    path("settings/", views.portal_settings, name="portal_settings"),
    # 4.2C — Catalog routes
    path("settings/categories/", views.categories_list, name="categories_list"),
    path("settings/categories/add/", views.category_create, name="category_create"),
    path("settings/categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("settings/categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("settings/items/", views.items_list, name="items_list"),
    path("settings/items/<int:pk>/toggle-availability/",views.item_toggle_available,name="item_toggle_available",),
    path("settings/items/add/", views.item_create, name="item_create"),
    path("settings/items/<int:pk>/edit/", views.item_edit, name="item_edit"),
    path("settings/items/<int:pk>/delete/", views.item_delete, name="item_delete"),


    # --- Live Board (relative paths; project urls.py prefixes with 'portal/') ---
    path("live/", views_live.live_board, name="live_board"),
    path("live/poll/", views_live.live_poll, name="live_poll"),
    path("live/<int:request_id>/action/", views_live.live_action, name="live_action"),
    path("live/<int:request_id>/detail/", views_live.live_detail, name="live_detail"),

    # History page (stub for now)
   
    path("requests/history/", views_live.history_view, name="portal_requests_history"),
    path("requests/<int:pk>/", views_live.request_detail, name="portal_request_detail"),
    path("requests/history/export.csv", views_live.history_export_csv, name="portal_requests_export_csv"),
   
   #7.2
   path("stay/checkin/", views_live.stay_checkin, name="portal_stay_checkin"),
   path("stay/checkout/", views_live.stay_checkout, name="portal_stay_checkout"),
   path("room/ready/", views_live.room_mark_ready, name="portal_room_ready"),

   #8.4
   path("stay/detail/", views_live.stay_detail_popup, name="portal_stay_detail_popup"),


    path("stay/detail-popup/", views_live.stay_detail_popup, name="portal_stay_detail_popup"),
    path("stay/print/", views_live.stay_print_slip, name="portal_stay_print"),
    path("portal/stay/checkout-confirm/", views_live.stay_checkout_confirm, name="portal_stay_checkout_confirm"),
    
    
    path("stays/", views_live.stays_history_view, name="portal_stays_history"),
    path("stays/export.csv", views_live.stays_export_csv, name="portal_stays_export_csv"),
    path("stays/<int:pk>/", views_live.stay_detail_page, name="portal_stay_detail"),

    path("settings/invoice/", views.settings_invoice, name="settings_invoice"),

    path("stays/<int:pk>/invoice/", views_live.stay_invoice, name="portal_stay_invoice"),
    
    path("stays/<int:pk>/mark-paid/", views_live.stay_mark_paid, name="portal_stay_mark_paid"),
    path("billing/stays/",views_billing.billing_stays_list,name="portal_billing_stays"),
    path("billing/", views_live.billing_list, name="portal_billing_list"),
    path("billing/export.csv", views_billing.billing_export_csv, name="portal_billing_export"),

    path("requests/<int:pk>/whatsapp/",views_live.portal_request_whatsapp,name="portal_request_whatsapp"), 
    path("rooms/<int:room_id>/whatsapp/",views_live.portal_room_whatsapp,name="portal_room_whatsapp"),
    path("settings/whatsapp-templates/",views_live.portal_whatsapp_templates,name="portal_whatsapp_templates"),
    path("billing/expired/", views_live.portal_expired_page, name="portal_expired_page"),


]








from django.urls import path, include
from . import views 

urlpatterns = [
    #url(r'^selectable/', include('selectable.urls')),
    path('selectable/', include('selectable.urls')),
# úvodní část serveru - fialový podklad
    path("", views.SoutezIndex.as_view(), name="index_souteze"),
    path("registrace/", views.RegistraceIndex.as_view(), name="registrace_souteze"),   
    path("pravidla/", views.SoutezPravidla.as_view(), name="pravidla"),
    path("vysledky/", views.SoutezVysledky.as_view(), name="vysledky"),
    path('vysledek/<int:pk>', views.SoutezVysledkyDetail.as_view(), name='vysledek-detail'),
    path('potvrzeni/<str:skey>', views.RegistracePotvrzeni.as_view(), name='registrace-potvrzeni'),

# herní část - modrý podklad
    path("hra/", views.HraIndex.as_view(), name="herni_server"),
    path("hra/login/", views.SoutezLogin.as_view(), name="login_souteze"),
    path("hra/logout/", views.SoutezLogout.as_view(), name="logout_souteze"),

    path('hra/udalostitymu/', views.HraUdalostitymu.as_view(), name="hra_udalostitymu"),
    path("hra/leaderboard", views.HraVysledky.as_view(), name="hra_vysledky"),

    path('hra/otazka/<int:pk>', views.HraOtazkaDetail.as_view(), name="otazka-detail"),
    path("hra/otazka/buy/<str:obtiznost>/<int:bazar>", views.KoupitOtazku.as_view(), name="koupit_otazku"),

    path('hra/chat/', views.TymChatList.as_view(), name="tym_chat_list"),
    path('hra/chat/<int:pk>', views.TymChat.as_view(), name='tym_chat'),

# administrační část - zelený podklad
    path("admin/", views.AdministraceIndex.as_view(), name="admin_index"),
    path("admin/login", views.AdminLogin.as_view(), name="admin_login"),
    path("admin/logout", views.AdminLogout.as_view(), name="admin_logout"),

    path("admin/novaotazka/", views.NovaOtazka.as_view(), name="nova_otazka"),
    path("admin/otazky/", views.Otazky.as_view(), name="otazky"),
    path("admin/detailotazky/<int:pk>", views.OtazkaAdminDetail.as_view(), name="admin-otazka-detail"),
    path("admin/smazotazku/<int:pk>", views.OtazkaAdminDelete.as_view(), name="admin-otazka-delete"),

    path("admin/kontrola/", views.KontrolaOdpovediIndex.as_view(), name="kontrola_odpovedi"),
    path("admin/kontrola/<int:pk>", views.KontrolaOdpovediDetail.as_view(), name="kontola_odpovedi_detail"),

    path("admin/soutez/", views.AdminSoutez.as_view(), name="admin_soutez"),
    path("admin/novasoutez/", views.AdminNovaSoutez.as_view(), name="nova_soutez"),
    path("admin/detailsoutez/<int:pk>", views.AdminSoutezDetail.as_view(), name="admin_soutez_detail"),

    path("admin/pdfzadani/<int:pk>", views.AdminPDFZadani.as_view(), name="admin_pdf_zadani"),
    path("admin/pdfvysledky/<int:pk>", views.AdminPDFVysledky.as_view(), name="admin_pdf_vysledky"),
    path("admin/email/<int:soutez>", views.EmailInfo.as_view(), name="admin_email_info"),

    path("admin/podpora/", views.PodporaChatList.as_view(), name="podpora_list"),
    path("admin/podpora/<int:pk>", views.PodporaChat.as_view(), name="podpora_chat"),

#jsapi
    path("jsapi/hra_index", views.HraIndexJsAPI.as_view(), name="hra_index_jsapi"),
    path("jsapi/hra_vysledky", views.SoutezVysledkyJsAPI.as_view(), name="hra_vysledky_jsapi"),
    path("jsapi/kontrola", views.KontrolaOdpovediJsAPI.as_view(), name="jsapi_kontrola"),

    path("jsapi/chat/view", views.ChatListJsAPI.as_view(), name="view_chat"),
    path("jsapi/chat/send", views.ChatSend.as_view(), name="send_chat"),
    path('jsapi/chat/list', views.ConvoListJsAPI.as_view(), name="convo_list"),
]

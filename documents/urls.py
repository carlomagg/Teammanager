from django.urls import path
from .views import create_document, document_list, home, send_approved_email, autocomplete_sales_rep, create_from_editor
from .viewfuncs.editor_docs import generate_pdf_view, edit_editor_document


urlpatterns = [
    path("create/", create_document, name="create_document"),
    path("list/", document_list, name="document_list"),
    # path("", home, name="document_home"),  # Renamed to avoid conflict
    path('autocomplete/sales-rep/', autocomplete_sales_rep, name='autocomplete_sales_rep'),
    path("create-editor/", create_from_editor, name="create_from_editor"),
    path("generate-pdf/<int:document_id>/", generate_pdf_view, name="generate_pdf"),
    path("edit-editor/<int:document_id>/", edit_editor_document, name="edit_editor_document"),
]
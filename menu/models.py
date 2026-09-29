from django.db import models

# Create your models here.
# menu/models.py

class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="menu/", blank=True)
    is_available = models.BooleanField(default=True)

    def dapatkan_status(self):
        return "Tersedia" if self.is_available else "Sedang Kosong"

    def __str__(self):
        return self.name
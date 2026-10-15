from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class PackagingLineBase(BaseModel):
    line_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    plant: str = Field(..., min_length=1)
    io_protocol: str = Field(default="DIRECT_API")
    shared_folder_path: Optional[str] = None
    sftp_host: Optional[str] = None
    sftp_port: Optional[int] = 22
    sftp_user: Optional[str] = None
    sftp_password: Optional[str] = None
    sftp_drop_folder: Optional[str] = None
    sftp_inbound_folder: Optional[str] = None
    api_endpoint: Optional[str] = None
    is_active: bool = True

class PackagingLineCreate(PackagingLineBase):
    pass

class PackagingLineUpdate(BaseModel):
    name: Optional[str] = None
    plant: Optional[str] = None
    io_protocol: Optional[str] = None
    shared_folder_path: Optional[str] = None
    sftp_host: Optional[str] = None
    sftp_port: Optional[int] = None
    sftp_user: Optional[str] = None
    sftp_password: Optional[str] = None
    sftp_drop_folder: Optional[str] = None
    sftp_inbound_folder: Optional[str] = None
    api_endpoint: Optional[str] = None
    is_active: Optional[bool] = None

class PackagingLineResponse(PackagingLineBase):
    created_at: str
    model_config = ConfigDict(from_attributes=True)

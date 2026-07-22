from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from backend.app.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    SessionPrincipal,
    client_ip,
    get_auth_service,
    require_same_origin,
    require_session,
)
from backend.app.calendar import CalendarMonthResult, CalendarUnavailableError
from backend.app.errors import ApiError
from backend.app.money import (
    MoneyFormatError,
    format_amount,
    format_grouped_amount,
    format_quick_read,
    from_uppercase,
    parse_amount,
    to_english,
    to_uppercase,
)
from backend.app.reminders import EmailDeliveryError, SmtpNotConfiguredError
from backend.app.tax_profile import (
    Catalog,
    InvalidTaxSettingError,
    TaxProfileService,
    TaxToolSettings,
    filter_events,
)
from backend.app.tax_source import Region, YearMonth

CurrentPrincipal = Annotated[SessionPrincipal, Depends(require_session)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class CurrentUserResponse(BaseModel):
    username: str


class AmountRequest(BaseModel):
    amount: str


class UppercaseRequest(BaseModel):
    uppercase: str


class MoneyConversionResponse(BaseModel):
    amount: str
    uppercase: str
    grouped: str
    quick_read: str
    english: str
    normalization_note: str | None = None


class RegionResponse(BaseModel):
    code: str
    name: str
    region_code: str


class CalendarEventResponse(BaseModel):
    source_event_id: str
    start_date: date
    end_date: date
    bssz: str
    split_items: list[str]
    source_agency: str | None
    source_created_at: str | None
    source_order: int


class CalendarResponse(BaseModel):
    region_code: str
    month: str
    official_events: list[CalendarEventResponse]
    personalized_events: list["PersonalizedEventResponse"]
    profile_complete: bool
    stale: bool
    sync_status: str
    last_succeeded_at: datetime | None
    source_url: str


class CalendarSyncRequest(BaseModel):
    region_code: str
    month: str


class PersonalizedEventResponse(BaseModel):
    key: str
    source_event_id: str
    category: str
    item_code: str | None
    display_name: str
    official_text: str
    matched_text: str
    start_date: date
    end_date: date
    source_order: int
    needs_confirmation: bool


class TaxToolSettingsResponse(BaseModel):
    default_mode: str
    taxpayer_type: str | None
    selected_item_codes: list[str]
    default_region_code: str | None
    reminder_days: list[int]
    profile_complete: bool
    email_configured: bool


class CatalogItemResponse(BaseModel):
    code: str
    category: str
    display_name: str
    taxpayer_scope: list[str]


class TestEmailResponse(BaseModel):
    status: str


def build_api_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/auth/login", status_code=204)
    def login(payload: LoginRequest, request: Request, response: Response) -> None:
        service = get_auth_service(request)
        token = service.authenticate(
            client_ip(request),
            payload.username,
            payload.password,
        )
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            secure=service.settings.cookie_secure,
            samesite="lax",
            path="/",
        )

    @router.post(
        "/auth/logout",
        status_code=204,
        dependencies=[Depends(require_session), Depends(require_same_origin)],
    )
    def logout(response: Response) -> None:
        response.delete_cookie(key=SESSION_COOKIE, path="/", samesite="lax")

    @router.get("/auth/me", response_model=CurrentUserResponse)
    def current_user(principal: CurrentPrincipal) -> CurrentUserResponse:
        return CurrentUserResponse(username=principal.username)

    protected_write_dependencies = [Depends(require_session), Depends(require_same_origin)]

    @router.get("/regions", response_model=list[RegionResponse])
    def regions(_: CurrentPrincipal, request: Request) -> list[RegionResponse]:
        return [RegionResponse(**region.__dict__) for region in request.app.state.regions]

    @router.get("/calendar", response_model=CalendarResponse)
    async def calendar_month(
        region_code: str,
        month: str,
        _: CurrentPrincipal,
        request: Request,
    ) -> CalendarResponse:
        selected_region = _validate_region(request.app.state.regions, region_code)
        selected_month = _parse_month(month)
        try:
            result = await request.app.state.calendar_service.get_month(
                selected_region.code,
                selected_month,
            )
        except CalendarUnavailableError as error:
            raise ApiError(
                status_code=503,
                code="calendar_unavailable",
                message="税历暂时不可用，请稍后重试",
            ) from error
        profile_service: TaxProfileService = request.app.state.tax_profile_service
        return _calendar_response(
            result,
            profile_service.get_settings(),
            profile_service.catalog,
        )

    @router.post(
        "/tools/tax/sync",
        response_model=CalendarResponse,
        dependencies=protected_write_dependencies,
    )
    async def sync_calendar(payload: CalendarSyncRequest, request: Request) -> CalendarResponse:
        selected_region = _validate_region(request.app.state.regions, payload.region_code)
        selected_month = _parse_month(payload.month)
        try:
            result = await request.app.state.calendar_service.sync_month(
                selected_region.code,
                selected_month,
            )
        except CalendarUnavailableError as error:
            raise ApiError(
                status_code=503,
                code="calendar_unavailable",
                message="税历同步失败，请稍后重试",
            ) from error
        profile_service: TaxProfileService = request.app.state.tax_profile_service
        return _calendar_response(
            result,
            profile_service.get_settings(),
            profile_service.catalog,
        )

    @router.get("/tools/tax/settings", response_model=TaxToolSettingsResponse)
    def get_tax_settings(_: CurrentPrincipal, request: Request) -> TaxToolSettingsResponse:
        return _settings_response(
            request.app.state.tax_profile_service.get_settings(),
            email_configured=request.app.state.settings.email_configured,
        )

    @router.get("/tools/tax/catalog", response_model=list[CatalogItemResponse])
    def get_tax_catalog(_: CurrentPrincipal, request: Request) -> list[CatalogItemResponse]:
        catalog: Catalog = request.app.state.tax_profile_service.catalog
        return [
            CatalogItemResponse(
                code=item.code,
                category=item.category,
                display_name=item.display_name,
                taxpayer_scope=list(item.taxpayer_scope),
            )
            for item in catalog.items
        ]

    @router.put(
        "/tools/tax/settings",
        response_model=TaxToolSettingsResponse,
        dependencies=protected_write_dependencies,
    )
    def update_tax_settings(
        payload: TaxToolSettings,
        request: Request,
    ) -> TaxToolSettingsResponse:
        try:
            stored = request.app.state.tax_profile_service.save_settings(payload)
        except InvalidTaxSettingError as error:
            raise ApiError(
                status_code=422,
                code=error.code,
                message=error.message,
            ) from error
        return _settings_response(
            stored,
            email_configured=request.app.state.settings.email_configured,
        )

    @router.post(
        "/tools/tax/test-email",
        response_model=TestEmailResponse,
        dependencies=protected_write_dependencies,
    )
    async def send_test_email(request: Request) -> TestEmailResponse:
        try:
            await request.app.state.reminder_service.send_test_email()
        except SmtpNotConfiguredError as error:
            raise ApiError(
                status_code=422,
                code="smtp_not_configured",
                message="邮件提醒尚未配置",
            ) from error
        except EmailDeliveryError as error:
            raise ApiError(
                status_code=503,
                code="email_delivery_failed",
                message="测试邮件发送失败，请检查 SMTP 配置",
            ) from error
        return TestEmailResponse(status="sent")

    @router.post(
        "/money/to-uppercase",
        response_model=MoneyConversionResponse,
        dependencies=protected_write_dependencies,
    )
    def money_to_uppercase(payload: AmountRequest) -> MoneyConversionResponse:
        try:
            amount = parse_amount(payload.amount)
        except MoneyFormatError as error:
            raise ApiError(
                status_code=422,
                code="invalid_money_format",
                message=str(error),
            ) from error
        return _money_response(amount)

    @router.post(
        "/money/to-number",
        response_model=MoneyConversionResponse,
        dependencies=protected_write_dependencies,
    )
    def money_to_number(payload: UppercaseRequest) -> MoneyConversionResponse:
        try:
            amount = from_uppercase(payload.uppercase)
        except MoneyFormatError as error:
            raise ApiError(
                status_code=422,
                code="invalid_money_format",
                message=str(error),
            ) from error
        normalization_note = (
            "已按标准写法转换：“圆”应写作“元”。" if "圆" in payload.uppercase else None
        )
        return _money_response(amount, normalization_note=normalization_note)

    return router


def _money_response(
    amount: Decimal,
    *,
    normalization_note: str | None = None,
) -> MoneyConversionResponse:
    return MoneyConversionResponse(
        amount=format_amount(amount),
        uppercase=to_uppercase(amount),
        grouped=format_grouped_amount(amount),
        quick_read=format_quick_read(amount),
        english=to_english(amount),
        normalization_note=normalization_note,
    )


def _validate_region(regions: list[Region], region_code: str) -> Region:
    for region in regions:
        if region.code == region_code:
            return region
    raise ApiError(
        status_code=422,
        code="invalid_region",
        message="请选择支持的税务地区",
    )


def _parse_month(value: str) -> YearMonth:
    try:
        return YearMonth.parse(value)
    except ValueError as error:
        raise ApiError(
            status_code=422,
            code="invalid_month",
            message="月份格式必须为 YYYY-MM",
        ) from error


def _calendar_response(
    result: CalendarMonthResult,
    settings: TaxToolSettings,
    catalog: Catalog,
) -> CalendarResponse:
    personalized = filter_events(result.events, settings, catalog)
    return CalendarResponse(
        region_code=result.region_code,
        month=str(result.month),
        official_events=[
            CalendarEventResponse(
                source_event_id=event.source_event_id,
                start_date=event.start_date,
                end_date=event.end_date,
                bssz=event.bssz,
                split_items=list(event.split_items),
                source_agency=event.source_agency,
                source_created_at=event.source_created_at,
                source_order=event.source_order,
            )
            for event in result.events
        ],
        personalized_events=[PersonalizedEventResponse(**event.__dict__) for event in personalized],
        profile_complete=settings.profile_complete,
        stale=result.stale,
        sync_status=result.sync_status,
        last_succeeded_at=result.last_succeeded_at,
        source_url=result.source_url,
    )


def _settings_response(
    settings: TaxToolSettings,
    *,
    email_configured: bool,
) -> TaxToolSettingsResponse:
    return TaxToolSettingsResponse(
        **settings.model_dump(),
        profile_complete=settings.profile_complete,
        email_configured=email_configured,
    )

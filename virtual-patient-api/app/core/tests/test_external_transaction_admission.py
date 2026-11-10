import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

import pytest
from fastapi import HTTPException

from app.core.database import admit_external_transaction, admit_review_transaction


def test_external_transaction_admission_reserves_capacity_and_releases_slots():
    admit = asynccontextmanager(admit_external_transaction)

    async def check():
        async with AsyncExitStack() as stack:
            for _ in range(4):
                await stack.enter_async_context(admit())
            with pytest.raises(HTTPException) as failure:
                await stack.enter_async_context(admit())
            assert failure.value.status_code == 503
        async with admit():
            pass

    asyncio.run(check())


def test_reviews_leave_room_for_patient_replies():
    review = asynccontextmanager(admit_review_transaction)
    reply = asynccontextmanager(admit_external_transaction)

    async def check():
        async with review(), review():
            with pytest.raises(HTTPException) as failure:
                async with review():
                    pass
            assert failure.value.status_code == 503
            async with reply(), reply():
                pass
        async with review():
            pass

    asyncio.run(check())

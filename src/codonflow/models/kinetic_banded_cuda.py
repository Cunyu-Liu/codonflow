"""Optional Triton kernels for O(L) banded kinetic linear algebra."""
import torch
import triton
import triton.language as tl


@triton.jit
def sm_kernel(
    lower_ptr, diagonal_ptr, upper_ptr, rank_ptr, rhs_ptr, output_ptr, denominator_ptr,
    work_l_ptr, work_d_ptr, work_u_ptr, work_u2_ptr, work_p_ptr, work_y_ptr,
    size, transpose: tl.constexpr,
):
    batch = tl.program_id(0)
    offset = batch * size
    lower_offset = batch * (size - 1)
    second_offset = batch * (size - 2)
    rhs_offset = batch * size * 2
    for index in range(size - 1):
        d = tl.load(work_d_ptr + offset + index)
        l = tl.load(work_l_ptr + lower_offset + index)
        u = tl.load(work_u_ptr + lower_offset + index)
        dn = tl.load(work_d_ptr + offset + index + 1)
        interchange = tl.abs(l) > tl.abs(d)
        pivot = tl.where(interchange, l, d)
        safe_pivot = tl.where(pivot != 0, pivot, 1.0)
        multiplier = tl.where(interchange, d, l) / safe_pivot
        no_swap_next = dn - multiplier * u
        swapped_next = u - multiplier * dn
        tl.store(work_d_ptr + offset + index, tl.where(interchange, l, d))
        tl.store(work_u_ptr + lower_offset + index, tl.where(interchange, dn, u))
        tl.store(work_d_ptr + offset + index + 1, tl.where(interchange, swapped_next, no_swap_next))
        tl.store(work_l_ptr + lower_offset + index, multiplier)
        tl.store(work_p_ptr + lower_offset + index, interchange.to(tl.int1))
        if index < size - 2:
            following_upper = tl.load(work_u_ptr + lower_offset + index + 1)
            tl.store(work_u2_ptr + second_offset + index, tl.where(interchange, following_upper, 0.0))
            tl.store(work_u_ptr + lower_offset + index + 1, tl.where(interchange, -multiplier * following_upper, following_upper))
    if transpose:
        for index in range(size):
            diagonal = tl.load(work_d_ptr + offset + index)
            safe_diagonal = tl.where(diagonal != 0, diagonal, 1.0)
            for component in range(2):
                value = tl.load(work_y_ptr + rhs_offset + index * 2 + component)
                if index > 0:
                    band = tl.load(work_u_ptr + lower_offset + index - 1)
                    previous = tl.load(work_y_ptr + rhs_offset + (index - 1) * 2 + component)
                    value -= band * previous
                if index > 1:
                    band2 = tl.load(work_u2_ptr + second_offset + index - 2)
                    previous2 = tl.load(work_y_ptr + rhs_offset + (index - 2) * 2 + component)
                    value -= band2 * previous2
                tl.store(work_y_ptr + rhs_offset + index * 2 + component, value / safe_diagonal)
        for reverse in range(size - 1):
            index = size - 2 - reverse
            multiplier = tl.load(work_l_ptr + lower_offset + index)
            interchange = tl.load(work_p_ptr + lower_offset + index)
            for component in range(2):
                current = tl.load(work_y_ptr + rhs_offset + index * 2 + component)
                following = tl.load(work_y_ptr + rhs_offset + (index + 1) * 2 + component)
                current -= multiplier * following
                tl.store(work_y_ptr + rhs_offset + index * 2 + component, tl.where(interchange, following, current))
                tl.store(work_y_ptr + rhs_offset + (index + 1) * 2 + component, tl.where(interchange, current, following))
    else:
        for index in range(size - 1):
            multiplier = tl.load(work_l_ptr + lower_offset + index)
            interchange = tl.load(work_p_ptr + lower_offset + index)
            for component in range(2):
                current = tl.load(work_y_ptr + rhs_offset + index * 2 + component)
                following = tl.load(work_y_ptr + rhs_offset + (index + 1) * 2 + component)
                no_swap = following - multiplier * current
                swapped_next = current - multiplier * following
                tl.store(work_y_ptr + rhs_offset + index * 2 + component, tl.where(interchange, following, current))
                tl.store(work_y_ptr + rhs_offset + (index + 1) * 2 + component, tl.where(interchange, swapped_next, no_swap))
        diagonal = tl.load(work_d_ptr + offset + size - 1)
        safe_diagonal = tl.where(diagonal != 0, diagonal, 1.0)
        for component in range(2):
            value = tl.load(work_y_ptr + rhs_offset + (size - 1) * 2 + component)
            tl.store(work_y_ptr + rhs_offset + (size - 1) * 2 + component, value / safe_diagonal)
        if size > 1:
            band = tl.load(work_u_ptr + lower_offset + size - 2)
            diagonal = tl.load(work_d_ptr + offset + size - 2)
            safe_diagonal = tl.where(diagonal != 0, diagonal, 1.0)
            for component in range(2):
                value = tl.load(work_y_ptr + rhs_offset + (size - 2) * 2 + component)
                following = tl.load(work_y_ptr + rhs_offset + (size - 1) * 2 + component)
                tl.store(work_y_ptr + rhs_offset + (size - 2) * 2 + component, (value - band * following) / safe_diagonal)
        for reverse in range(size - 2):
            index = size - 3 - reverse
            band = tl.load(work_u_ptr + lower_offset + index)
            band2 = tl.load(work_u2_ptr + second_offset + index)
            diagonal = tl.load(work_d_ptr + offset + index)
            safe_diagonal = tl.where(diagonal != 0, diagonal, 1.0)
            for component in range(2):
                value = tl.load(work_y_ptr + rhs_offset + index * 2 + component)
                following = tl.load(work_y_ptr + rhs_offset + (index + 1) * 2 + component)
                following2 = tl.load(work_y_ptr + rhs_offset + (index + 2) * 2 + component)
                tl.store(work_y_ptr + rhs_offset + index * 2 + component, (value - band * following - band2 * following2) / safe_diagonal)
    first_last = tl.load(work_y_ptr + rhs_offset + (size - 1) * 2)
    second_last = tl.load(work_y_ptr + rhs_offset + (size - 1) * 2 + 1)
    if transpose:
        denominator = second_last * 0.0 + 1.0
        numerator = second_last * 0.0
        for index in range(size):
            rank = tl.load(rank_ptr + offset + index)
            first = tl.load(work_y_ptr + rhs_offset + index * 2)
            second = tl.load(work_y_ptr + rhs_offset + index * 2 + 1)
            denominator -= rank * second
            numerator += rank * first
    else:
        denominator = 1.0 - second_last
        numerator = first_last
    safe_denominator = tl.where(tl.abs(denominator) > 64 * 2.220446049250313e-16, denominator, 1.0)
    for index in range(size):
        first = tl.load(work_y_ptr + rhs_offset + index * 2)
        second = tl.load(work_y_ptr + rhs_offset + index * 2 + 1)
        tl.store(output_ptr + offset + index, first + second * numerator / safe_denominator)
    tl.store(denominator_ptr + batch, denominator)


def rank_one(bands, rhs, transpose=False):
    bands = tuple(value.contiguous() for value in bands)
    rhs = rhs.contiguous()
    lower, diagonal, upper, flux = bands
    batch, size = diagonal.shape
    base_diagonal = diagonal.clone()
    base_diagonal[:, -1] = -flux[:, -1]
    rank = -flux.clone()
    rank[:, -1] = -2 * flux[:, -1]
    second_rhs = rank if not transpose else torch.zeros_like(rhs)
    if transpose:
        second_rhs[:, -1] = 1.0
    work_y = torch.stack((rhs, second_rhs), dim=-1).contiguous()
    output = diagonal.new_empty((batch, size))
    denominator = diagonal.new_empty(batch)
    work_l = lower.clone()
    work_d = base_diagonal
    work_u = upper.clone()
    work_u2 = diagonal.new_empty((batch, size - 2))
    work_p = torch.empty((batch, size - 1), dtype=torch.bool, device=diagonal.device)
    sm_kernel[(batch,)](
        lower, diagonal, upper, rank, rhs, output, denominator,
        work_l, work_d, work_u, work_u2, work_p, work_y,
        size, transpose, num_warps=1,
    )
    return output, denominator


@triton.jit
def qr_kernel(
    lower_ptr, diagonal_ptr, upper_ptr, flux_ptr, rhs_ptr, output_ptr,
    work_d_ptr, work_u_ptr, work_u2_ptr, work_z_ptr, work_y_ptr,
    work_c_ptr, work_s_ptr,
    size, transpose: tl.constexpr,
):
    batch = tl.program_id(0)
    offset = batch * size
    lower_offset = batch * (size - 1)
    second_offset = batch * (size - 2)
    for index in range(size - 1):
        d = tl.load(work_d_ptr + offset + index)
        l = tl.load(lower_ptr + lower_offset + index)
        norm = tl.sqrt(d * d + l * l)
        safe_norm = tl.where(norm > 0, norm, 1.0)
        cosine = d / safe_norm
        sine = l / safe_norm
        tl.store(work_c_ptr + lower_offset + index, cosine)
        tl.store(work_s_ptr + lower_offset + index, sine)
        if index < size - 2:
            current_upper = tl.load(work_u_ptr + lower_offset + index)
            next_diagonal = tl.load(work_d_ptr + offset + index + 1)
            next_upper = tl.load(work_u_ptr + lower_offset + index + 1)
            tl.store(work_u_ptr + lower_offset + index, cosine * current_upper + sine * next_diagonal)
            tl.store(work_d_ptr + offset + index + 1, -sine * current_upper + cosine * next_diagonal)
            tl.store(work_u2_ptr + second_offset + index, sine * next_upper)
            tl.store(work_u_ptr + lower_offset + index + 1, cosine * next_upper)
        first_flux = tl.load(work_z_ptr + offset + index)
        second_flux = tl.load(work_z_ptr + offset + index + 1)
        tl.store(work_z_ptr + offset + index, cosine * first_flux + sine * second_flux)
        tl.store(work_z_ptr + offset + index + 1, -sine * first_flux + cosine * second_flux)
        first_rhs = tl.load(work_y_ptr + offset + index)
        second_rhs = tl.load(work_y_ptr + offset + index + 1)
        tl.store(work_y_ptr + offset + index, cosine * first_rhs + sine * second_rhs)
        tl.store(work_y_ptr + offset + index + 1, -sine * first_rhs + cosine * second_rhs)
        tl.store(work_d_ptr + offset + index, norm)
    final_flux = tl.load(work_z_ptr + offset + size - 1)
    tl.store(work_d_ptr + offset + size - 1, final_flux)
    if transpose:
        last_value = tl.load(rhs_ptr + offset + size - 1)
        for index in range(size - 1):
            value = tl.load(rhs_ptr + offset + index)
            if index > 0:
                previous = tl.load(output_ptr + offset + index - 1)
                band = tl.load(work_u_ptr + lower_offset + index - 1)
                value -= band * previous
            if index > 1:
                previous2 = tl.load(output_ptr + offset + index - 2)
                band2 = tl.load(work_u2_ptr + second_offset + index - 2)
                value -= band2 * previous2
            diagonal = tl.load(work_d_ptr + offset + index)
            safe_diagonal = tl.where(diagonal != 0, diagonal, 1.0)
            solved = value / safe_diagonal
            tl.store(output_ptr + offset + index, solved)
            band = tl.load(work_z_ptr + offset + index)
            last_value -= band * solved
        diagonal = tl.load(work_d_ptr + offset + size - 1)
        safe_diagonal = tl.where(diagonal != 0, diagonal, 1.0)
        tl.store(output_ptr + offset + size - 1, last_value / safe_diagonal)
        for reverse in range(size - 1):
            index = size - 2 - reverse
            cosine = tl.load(work_c_ptr + lower_offset + index)
            sine = tl.load(work_s_ptr + lower_offset + index)
            first = tl.load(output_ptr + offset + index)
            second = tl.load(output_ptr + offset + index + 1)
            tl.store(output_ptr + offset + index, cosine * first - sine * second)
            tl.store(output_ptr + offset + index + 1, sine * first + cosine * second)
    else:
        for reverse in range(size):
            index = size - 1 - reverse
            value = tl.load(work_y_ptr + offset + index)
            if index < size - 1:
                following = tl.load(output_ptr + offset + index + 1)
                band = tl.load(work_u_ptr + lower_offset + index)
                flux = tl.load(work_z_ptr + offset + index)
                last = tl.load(output_ptr + offset + size - 1)
                value -= band * following + flux * last
            if index < size - 2:
                following2 = tl.load(output_ptr + offset + index + 2)
                band2 = tl.load(work_u2_ptr + second_offset + index)
                value -= band2 * following2
            diagonal = tl.load(work_d_ptr + offset + index)
            safe_diagonal = tl.where(diagonal != 0, diagonal, 1.0)
            tl.store(output_ptr + offset + index, value / safe_diagonal)


def qr(bands, rhs, transpose=False):
    bands = tuple(value.contiguous() for value in bands)
    rhs = rhs.contiguous()
    lower, diagonal, upper, flux = bands
    batch, size = diagonal.shape
    work_d = diagonal.clone()
    work_u = upper.clone()
    work_u2 = diagonal.new_empty((batch, size - 2))
    work_z = flux.clone()
    work_y = rhs.clone()
    work_c = diagonal.new_empty((batch, size - 1))
    work_s = diagonal.new_empty((batch, size - 1))
    output = diagonal.new_empty((batch, size))
    qr_kernel[(batch,)](
        lower, diagonal, upper, flux, rhs, output,
        work_d, work_u, work_u2, work_z, work_y, work_c, work_s,
        size, transpose,
    )
    return output
